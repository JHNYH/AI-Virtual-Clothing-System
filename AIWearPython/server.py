import base64
import hashlib
import json
import os
import re
import tempfile
import urllib.request

from io import BytesIO
import uuid
import threading

# ============ 资源限制（必须在 import torch 之前设置）============
# 小内存 / 少核数的服务器上，PyTorch 默认按 CPU 核数开线程池、并且优先吃满内存，
# 表现为服务一启动 CPU 飙升、整机卡死。这里统一压到单线程，可用环境变量覆盖：
#   TORCH_NUM_THREADS=2  调整线程数
#   CLIP_ENABLED=false   完全不加载 CLIP 模型（关掉图片搜索能力，最省内存）
_TORCH_THREADS = str(os.getenv("TORCH_NUM_THREADS", "1"))
os.environ.setdefault("OMP_NUM_THREADS", _TORCH_THREADS)
os.environ.setdefault("MKL_NUM_THREADS", _TORCH_THREADS)
os.environ.setdefault("OPENBLAS_NUM_THREADS", _TORCH_THREADS)
os.environ.setdefault("NUMEXPR_NUM_THREADS", _TORCH_THREADS)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from langchain_core.tools import tool
from dashscope import MultiModalConversation
from deepagents import create_deep_agent

from PIL import Image
from dotenv import load_dotenv
from flask import Flask, request, jsonify
import redis
import torch
from transformers import CLIPModel, CLIPProcessor

from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate

# 与上面的环境变量保持一致，限制 PyTorch 使用的线程数
torch.set_num_threads(int(_TORCH_THREADS))

# 创建Flask实例
app = Flask(__name__)

# 获取配置信息
load_dotenv()

API_KEY = os.getenv("DASHSCOPE_API_KEY")

REDIS_HOST = os.getenv("REDIS_HOST", "118.190.217.49")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_TIMEOUT = 2.0
REDIS_MAX_CONNECTIONS = 8

CLIP_MODEL_PATH = r"C:\Users\JHNYH\Desktop\clip-vit-base-patch16\snapshots\master"

redis_pool = redis.ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    socket_timeout=REDIS_TIMEOUT,
    socket_connect_timeout=REDIS_TIMEOUT,
    decode_responses=True,
    max_connections=REDIS_MAX_CONNECTIONS,
)
redis_client = redis.Redis(connection_pool=redis_pool)

# CLIP 模型改为「首次用到时才加载」：启动阶段不再占用几百 MB 内存，
# 避免服务刚起来就把整台机器压垮。可用 CLIP_ENABLED=false 彻底关闭该能力。
CLIP_ENABLED = os.getenv("CLIP_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")

_clip_model = None
_clip_processor = None
_clip_failed = False
_clip_lock = threading.Lock()


def get_clip():
    """按需加载 CLIP 模型，只加载一次；失败后不再反复重试"""
    global _clip_model, _clip_processor, _clip_failed
    if not CLIP_ENABLED:
        raise RuntimeError("CLIP 已关闭（CLIP_ENABLED=false）")
    if _clip_failed:
        raise RuntimeError("CLIP 模型未启用")
    if _clip_model is None or _clip_processor is None:
        # 加锁避免并发请求把模型加载两遍，那会直接吃光内存
        with _clip_lock:
            if _clip_model is None or _clip_processor is None:
                try:
                    model = CLIPModel.from_pretrained(CLIP_MODEL_PATH, local_files_only=True)
                    processor = CLIPProcessor.from_pretrained(CLIP_MODEL_PATH, local_files_only=True)
                    model.eval()
                    _clip_model, _clip_processor = model, processor
                    print("CLIP 模型已经启用")
                except Exception as e:
                    _clip_failed = True
                    print(f"CLIP 模型未启用:{e}")
                    raise RuntimeError("CLIP 模型未启用")
    return _clip_model, _clip_processor


def download_image_from_url(image_url: str) -> bytes:
    req = urllib.request.Request(image_url, headers={"User-Agent": "AIWearPython/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


# 向量维度：CLIP ViT-B/16 固定 512。原先这个数字硬编码在多处，统一到这里。
VECTOR_DIM = 512


def make_image_id(user_id, oss_url: str) -> str:
    """Redis 记录的确定性 id：同一 (userId, ossUrl) 永远得到同一个 key。

    这样「同一张图重复上传 / 重复对账」天然幂等，不会产生重复的检索记录，
    也就省掉了额外维护一张去重索引的麻烦。
    """
    return hashlib.md5(f"{user_id}:{oss_url}".encode("utf-8")).hexdigest()


def _coerce_vector(vector):
    """校验并归一化向量；允许直接转发 MySQL 里存的 JSON 文本，
    避免在 Java 侧把 512 个 double 解析一遍再拼回去。"""
    if isinstance(vector, str):
        vector = json.loads(vector)
    if not isinstance(vector, list) or len(vector) != VECTOR_DIM:
        raise ValueError(f"向量维度必须为 {VECTOR_DIM}，实际为 "
                         f"{len(vector) if isinstance(vector, list) else type(vector).__name__}")
    return [float(x) for x in vector]


def encode_image_vector(image_data: bytes) -> list:
    clip_model, clip_processor = get_clip()
    img = Image.open(BytesIO(image_data)).convert("RGB")
    inputs = clip_processor(images=img, return_tensors="pt")
    with torch.no_grad():
        features = clip_model.get_image_features(**inputs)
        # transformers 5.x 起 get_image_features 返回 BaseModelOutputWithPooling 而非张量
        if not torch.is_tensor(features):
            features = features.pooler_output
        features = torch.nn.functional.normalize(features, p=2, dim=-1)
    vector = features[0].detach().cpu().tolist()
    if len(vector) != VECTOR_DIM:
        raise RuntimeError(f"CLIP 向量维度异常: {len(vector)}")
    return vector


def save_image_record_to_redis(record: dict) -> None:
    image_id = record["imageId"]
    user_id = record["userId"]
    payload = json.dumps(record, ensure_ascii=False)
    redis_client.set(f"aiwear:image:{image_id}", payload)
    redis_client.sadd(f"aiwear:user:{user_id}:images", image_id)


# 检索配置：CLIP 是英文模型，中文查询几乎没有区分度，需先翻译成英文再编码。
# 阈值原为 0.23，实测发现「正确匹配」的相似度就横跨该值两侧（人 0.2228、男模特 0.2642），
# 导致换个说法就从「有结果」变「没结果」（over-strict），故下调至 0.18；
# 明显不相关的查询（红色连衣裙 0.1085）仍在阈值之外，不会被召回来。
SEARCH_SCORE_THRESHOLD = 0.18
SEARCH_TOP_K = 20

# 图片类别：对应业务里的两类图片，检索时只返回与查询同类的图片
CATEGORY_CLOTHING = "clothing"
CATEGORY_PERSON = "person"
# 既不是衣物也不是人物（如汽车、风景），库中不可能有同类图片，直接返回空结果
CATEGORY_OTHER = "other"
CATEGORY_RULE = (
    "当前的业务只有两类图片：\n"
    "1) clothing：衣服/服装/穿搭（单品、平铺、挂拍、衣服特写等）\n"
    "2) person：人物人像（人脸照、半身照、全身照，画面主体是人）\n"
    "以上都不是的（如汽车、风景、食物、动物）算 other。\n"
    "画面主体是人的一律算 person，哪怕他穿着衣服。\n"
    "只输出 clothing、person 或 other 中的一个，不要任何其他内容"
)


def _parse_category(text: str) -> str:
    text = (text or "").strip().lower()
    if text.startswith(CATEGORY_PERSON):
        return CATEGORY_PERSON
    if text.startswith(CATEGORY_CLOTHING):
        return CATEGORY_CLOTHING
    if text.startswith(CATEGORY_OTHER):
        return CATEGORY_OTHER
    return ""


def classify_by_description(description: str) -> str:
    """按图片的文字描述判断类别；判不出来返回空字符串（检索时视为不限类别）"""
    if not description or not description.strip():
        return ""
    llm = ChatTongyi(
        model_name="qwen-plus",
        temperature=0.0,
        dashscope_api_key=API_KEY
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", CATEGORY_RULE),
            ("human", "图片文字描述: {description}"),
        ]
    )
    resp = llm.invoke(prompt.format_messages(description=description))
    return _parse_category(resp.content)


def classify_image(image_data: bytes) -> str:
    """按图片本身判断类别（图搜图用）；判不出来返回空字符串，保证搜索仍可用"""
    try:
        data_uri = process_image(image_data)
        vl_llm = ChatTongyi(
            model_name="qwen3-vl-plus",
            temperature=0.0,
            dashscope_api_key=API_KEY
        )
        human_content = [
            {"image": data_uri},
            {"text": CATEGORY_RULE + "\n请判断这张图片属于哪一类"},
        ]
        resp = vl_llm.invoke([HumanMessage(content=human_content)])
        content = resp.content
        text = content[0]["text"] if isinstance(content, list) else content
        return _parse_category(text)
    except Exception as e:
        print(f"判定上传图片类别失败:{e}")
        return ""


def translate_query_to_english(query: str) -> str:
    # 沿用本文件其他函数的写法：按需构建大模型实例
    try:
        llm = ChatTongyi(
            model_name="qwen-plus",
            temperature=0.0,
            dashscope_api_key=API_KEY
        )
        prompt = (
            "把下面的中文搜索词翻译成最适合图像检索的简短英文短语，"
            "只输出英文短语本身，不要任何解释、标点或引号。\n" + query
        )
        return llm.invoke(prompt).content.strip()
    except Exception as e:
        # 翻译失败退回原文，不阻断搜索
        print(f"翻译搜索词失败:{e}")
        return query


def encode_text_vector(text: str) -> list:
    clip_model, clip_processor = get_clip()
    inputs = clip_processor(text=[text], return_tensors="pt", padding=True)
    with torch.no_grad():
        features = clip_model.get_text_features(**inputs)
        # 与图像特征同理，transformers 5.x 起返回 BaseModelOutputWithPooling
        if not torch.is_tensor(features):
            features = features.pooler_output
        features = torch.nn.functional.normalize(features, p=2, dim=-1)
    vector = features[0].detach().cpu().tolist()
    if len(vector) != VECTOR_DIM:
        raise RuntimeError(f"CLIP 文本向量维度异常: {len(vector)}")
    return vector


def load_user_image_records(user_id) -> list:
    image_ids = list(redis_client.smembers(f"aiwear:user:{user_id}:images"))
    if not image_ids:
        return []
    # 批量取，避免逐条 GET 的 N 次网络往返
    pipe = redis_client.pipeline()
    for image_id in image_ids:
        pipe.get(f"aiwear:image:{image_id}")
    payloads = pipe.execute()

    records = []
    for image_id, payload in zip(image_ids, payloads):
        if not payload:
            continue
        record = json.loads(payload)
        # 老记录没有类别字段：按描述补判一次并写回，避免每次检索都重复判断
        if "category" not in record:
            record["category"] = classify_by_description(record.get("description", ""))
            redis_client.set(f"aiwear:image:{image_id}", json.dumps(record, ensure_ascii=False))
        records.append(record)
    return records


def reconcile_user_index(user_id, keep_oss_urls: list) -> dict:
    """对账：让某个用户的 Redis 索引与 MySQL 里的图片列表保持一致。

    keep_oss_urls 来自 MySQL（该用户的全部图片地址），是唯一事实来源。
    本函数只读向量记录、按 ossUrl 比对，不做任何重新计算——
    缺失的记录由调用方拿着 MySQL 里存的向量补写（毫秒级），而不是重新调大模型。

    返回 {"missing": [...], "removed": [...], "indexed": n, "skipped": bool}
    """
    keep = {url for url in (keep_oss_urls or []) if url}
    # 安全阀：拿不到 MySQL 的图片列表时绝不做任何删除，
    # 否则一次误读（空结果/查询失败）就会把用户的索引整个清空。
    if not keep:
        return {"missing": [], "removed": [], "indexed": 0, "skipped": True}

    index_key = f"aiwear:user:{user_id}:images"
    image_ids = list(redis_client.smembers(index_key))

    pipe = redis_client.pipeline()
    for image_id in image_ids:
        pipe.get(f"aiwear:image:{image_id}")
    payloads = pipe.execute()

    present = set()
    orphan_ids = []       # 记录还在，但 MySQL 里已经没有这张图 → 索引和记录都要删
    dangling_ids = []     # 索引里有指针，但记录已被删掉 → 只删索引里的指针
    removed = []

    for image_id, payload in zip(image_ids, payloads):
        if not payload:
            dangling_ids.append(image_id)
            continue
        url = json.loads(payload).get("ossUrl", "")
        if url not in keep:
            orphan_ids.append(image_id)
            removed.append(url)
            continue
        present.add(url)

    if orphan_ids:
        pipe = redis_client.pipeline()
        for image_id in orphan_ids:
            pipe.delete(f"aiwear:image:{image_id}")
        pipe.srem(index_key, *orphan_ids)
        pipe.execute()
    if dangling_ids:
        redis_client.srem(index_key, *dangling_ids)
        print(f"清理悬空索引指针 {len(dangling_ids)} 个：user={user_id}")

    missing = [url for url in keep if url not in present]
    return {"missing": missing, "removed": removed, "indexed": len(present), "skipped": False}


def search_similar(user_id, query_vector: list, category: str = "") -> list:
    # 只保留向量完整的记录，避免脏数据把整个检索拖垮
    records = [r for r in load_user_image_records(user_id)
               if r.get("vector") and len(r["vector"]) == VECTOR_DIM]
    # 只返回与查询同类的图片（传衣物只出衣物，传人物只出人物）
    if category:
        records = [r for r in records if r.get("category") == category]
    if not records:
        return []

    matrix = torch.nn.functional.normalize(
        torch.tensor([r["vector"] for r in records], dtype=torch.float32), p=2, dim=-1
    )
    query = torch.nn.functional.normalize(
        torch.tensor(query_vector, dtype=torch.float32), p=2, dim=-1
    )
    scores = (matrix @ query).tolist()

    ranked = sorted(zip(records, scores), key=lambda item: item[1], reverse=True)
    # 返回 (记录, 分数)，便于后续按描述复核相关性
    return [(r, float(score)) for r, score in ranked[:SEARCH_TOP_K]
            if score >= SEARCH_SCORE_THRESHOLD]


def to_search_response(ranked: list) -> list:
    return [{"filePath": r.get("ossUrl", ""), "score": round(score, 4)} for r, score in ranked]


def filter_clearly_irrelevant(query: str, ranked: list) -> list:
    """CLIP 的文图相似度区分度有限，再用大模型剔除明显不相关的结果（拿不准的一律保留）"""
    if not ranked:
        return ranked
    lines = [f"{i}. {r.get('description', '')}" for i, (r, _) in enumerate(ranked)]
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是一个图片检索复核助手。用户会给出一个搜索词和若干候选图片的描述。"
                "请只挑出其中明显不相关、与搜索词不是同一类事物的候选，列出它们的编号。"
                "拿不准的一律算相关，不要列出。"
                "只输出需要排除的编号，用逗号分隔；如果没有需要排除的，只输出：无。不要任何解释",
            ),
            ("human", "搜索词：{query}\n\n候选图片：\n{lines}"),
        ]
    )
    llm = ChatTongyi(
        model_name="qwen-plus",
        temperature=0.0,
        dashscope_api_key=API_KEY
    )
    text = llm.invoke(prompt.format_messages(query=query, lines="\n".join(lines))).content.strip()
    excluded = {int(n) for n in re.findall(r"\d+", text)}
    return [item for i, item in enumerate(ranked) if i not in excluded]


# 将图片bytes转换成base_uri
def process_image(image_data : bytes) -> str:
    img = Image.open(BytesIO(image_data))
    image_format = (img.format).lower()
    image_base64 = base64.b64encode(image_data).decode("utf-8")
    data_uri = f"data:{image_format};base64,{image_base64}"
    return data_uri

# 调用大模型生成图片文字描述信息
def describe_image(image_data : bytes) -> str:
    try:
        # 1. 先把图片转化成base64
        data_uri = process_image(image_data)
        # 2. 构建LangChain的请求
        human_content = [
            {"image": data_uri},
            {
                "text": (
                    "用一句话简要地概括这张图片的内容，"
                    "并给出3到5个关键词（使用逗号分隔开），不要过多地解释"
                )
            },
        ]
        # 3. 构建访问大模型的实例
        vl_llm = ChatTongyi(
            model_name="qwen3-vl-plus",
            temperature=0.0,
            dashscope_api_key=API_KEY
        )
        # 4. 把访问大模型得到的结果进行处理返回
        resp = vl_llm.invoke([HumanMessage(content=human_content)])
        return resp.content[0]['text']
    except Exception as e:
        print(f"生成图片的文字描述信息出现异常:{e}")
        return ""




# 对图片的描述信息做最终的判定
def validate_image(image_desc : str) -> bool:
   try:
       prompt = ChatPromptTemplate.from_messages(
           [
               (
                   "system",
                   "你是一个图片审核助手，当前的业务只需要两种图片："
                   "1) 衣服/服装/穿搭相关;"
                   "2) 人物人像(人脸照、半身照、全身照).\n"
                   "需要你来判断当前图片的内容是否是以上两类图片，如果是输出是，如果否输出否。"
                   "请严格只输出是或者否，不要别的内容"
               ),
               (
                   "human", f"图片文字描述: {image_desc}"
               )
           ]
       )

       llm = ChatTongyi(
           model_name="qwen-plus",
           temperature=0.7,
           dashscope_api_key=API_KEY
       )

       resp = llm.invoke(prompt.format_messages())
       text = resp.content
       return text.startswith("是")
   except Exception as e:
       print(f"做图片内容判定的时候出现异常:{e}")
       return False


# 定义审核图片的接口路由
@app.route("/api/validate-image", methods = ["POST"])
def validate_image_api():
    try:
        file = request.files["file"]
        image_data = file.read()
        desc = describe_image(image_data) # 调用大模型生成图片文字描述信息
        allow = validate_image(desc)     # 二次调用大模型，处理文字描述信息判断当前图片是否符合要求
        return jsonify({"code":200, "allow": allow}), 200
    except Exception as e:
        print(f"执行审核图片操作捕获异常:{e}")
        return jsonify({"code":500, "error": False}), 500


def analyze_oss_image(oss_url: str) -> dict:
    """下载 OSS 图片，生成文字描述、类别与 CLIP 向量。只计算，不落任何存储。"""
    image_data = download_image_from_url(oss_url)
    description = describe_image(image_data)
    return {
        "description": description,
        "category": classify_by_description(description),
        "vector": encode_image_vector(image_data),
    }


def _read_user_and_oss_url():
    """两个新接口共用的取值逻辑：JSON body 优先，兼容 form 与 url 别名"""
    data = request.get_json(silent=True) or {}
    user_id = data.get("userId") or request.form.get("userId")
    oss_url = (
        data.get("ossUrl")
        or data.get("url")
        or request.form.get("ossUrl")
        or request.form.get("url")
    )
    return user_id, oss_url


# 定义上传图片的接口路由：接收 OSS 地址与 userId，生成描述和 CLIP 向量后写入 Redis
@app.route("/api/upload-image", methods=["POST"])
def upload_image_api():
    try:
        user_id, oss_url = _read_user_and_oss_url()
        if not user_id or not oss_url:
            return jsonify({
                "success": False,
                "error": "userId 和 ossUrl 不能为空"
            }), 400

        analyzed = analyze_oss_image(oss_url)
        image_id = make_image_id(user_id, oss_url)
        record = {
            "imageId": image_id,
            "userId": user_id,
            "ossUrl": oss_url,
            "description": analyzed["description"],
            "vector": analyzed["vector"],
            "category": analyzed["category"],
        }
        save_image_record_to_redis(record)
        return jsonify({
            "success": True,
            "imageId": image_id,
            "userId": user_id,
            "description": analyzed["description"],
        }), 200
    except Exception as e:
        print(f"上传图片处理失败:{e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# 定义「只分析不入库」的接口：返回描述/类别/向量，由调用方负责持久化
# 上传链路改成「先落库（MySQL 连向量一起存）、后建索引」后，用这个接口拿计算结果
@app.route("/api/analyze-image", methods=["POST"])
def analyze_image_api():
    try:
        user_id, oss_url = _read_user_and_oss_url()
        if not user_id or not oss_url:
            return jsonify({
                "success": False,
                "error": "userId 和 ossUrl 不能为空"
            }), 400

        analyzed = analyze_oss_image(oss_url)
        return jsonify({
            "success": True,
            "imageId": make_image_id(user_id, oss_url),
            "userId": user_id,
            "ossUrl": oss_url,
            "description": analyzed["description"],
            "category": analyzed["category"],
            "vector": analyzed["vector"],
        }), 200
    except Exception as e:
        print(f"分析图片失败:{e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# 定义「把已知记录写入索引」的接口：幂等，同一 (userId, ossUrl) 只会有一条记录。
# 对账时用它把 MySQL 里存的向量搬运回 Redis，不重新计算。
@app.route("/api/index-image", methods=["POST"])
def index_image_api():
    try:
        data = request.get_json(silent=True) or {}
        user_id = data.get("userId") or request.form.get("userId")
        oss_url = data.get("ossUrl") or request.form.get("ossUrl")
        if not user_id or not oss_url:
            return jsonify({
                "success": False,
                "error": "userId 和 ossUrl 不能为空"
            }), 400

        try:
            vector = _coerce_vector(data.get("vector") if data else request.form.get("vector"))
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

        image_id = make_image_id(user_id, oss_url)
        record = {
            "imageId": image_id,
            "userId": user_id,
            "ossUrl": oss_url,
            "description": data.get("description") or "",
            "vector": vector,
            "category": data.get("category") or "",
        }
        save_image_record_to_redis(record)
        return jsonify({"success": True, "imageId": image_id, "userId": user_id}), 200
    except Exception as e:
        print(f"写入图片索引失败:{e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# 定义对账接口：把该用户的索引与「MySQL 里的图片列表」对齐，返回缺失的地址供调用方补写
@app.route("/api/reconcile-user", methods=["POST"])
def reconcile_user_api():
    try:
        data = request.get_json(silent=True) or {}
        user_id = data.get("userId") or request.form.get("userId")
        if not user_id:
            return jsonify({"success": False, "error": "userId 不能为空"}), 400

        keep_oss_urls = data.get("keepOssUrls")
        if keep_oss_urls is None:
            keep_oss_urls = request.form.getlist("keepOssUrls")

        result = reconcile_user_index(user_id, keep_oss_urls)
        return jsonify({
            "success": True,
            "userId": user_id,
            "missing": result["missing"],
            "removed": result["removed"],
            "indexed": result["indexed"],
            "skipped": result["skipped"],
        }), 200
    except Exception as e:
        print(f"对账失败:{e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# 定义搜索图片的接口路由：有 file 走图搜图，否则用 query 走文搜图，返回该用户自己的图片
@app.route("/api/search-image", methods=["POST"])
def search_image_api():
    try:
        user_id = request.form.get("userId")
        if not user_id:
            return jsonify({"code": 400, "error": "缺少 userId"}), 400

        file = request.files.get("file")
        query = request.form.get("query")
        text_query = ""
        if file is not None:
            # 图搜图：按上传的图片判断类别
            image_data = file.read()
            query_vector = encode_image_vector(image_data)
            category = classify_image(image_data)
        elif query and query.strip():
            # 文搜图：按查询词判断类别
            text_query = query.strip()
            query_vector = encode_text_vector(translate_query_to_english(text_query))
            category = classify_by_description(text_query)
        else:
            return jsonify({"code": 400, "error": "query 与 file 至少需要一个"}), 400

        # 查询既不是衣物也不是人物时，库里不可能有同类图片
        if category == CATEGORY_OTHER:
            return jsonify({"code": 200, "data": []}), 200

        ranked = search_similar(user_id, query_vector, category)
        # 图搜图两边都是图像、相似度可靠；文搜图区分度有限，再剔除明显不相关的
        if text_query:
            ranked = filter_clearly_irrelevant(text_query, ranked)
        return jsonify({"code": 200, "data": to_search_response(ranked)}), 200
    except Exception as e:
        print(f"搜索图片处理失败:{e}")
        return jsonify({"code": 500, "error": str(e)}), 500


llm = ChatTongyi(
           model_name="qwen-plus",
           temperature=0.1,
           dashscope_api_key = API_KEY
)

@tool
def edit_image_tool(image_path: str, instruction: str) -> str:
    """编辑单张图片"
        输入本地图片地址路径与编辑指令   调用Dashscope的图像编辑模型生成新的URL
        返回JSON字符串: {"success": true, "url":"..."} 或 {"success": false, "error":"..."}
        """
    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
        image_data_uri = process_image(image_data)

        message = [
            {
                "role": "user",
                "content": [
                    {
                        "image": image_data_uri
                    },
                    {
                        "text": instruction
                    }
                ]
            }
        ]

        # 构建请求大模型的参数：签名是 messages（复数），且 MultiModalConversation 不会自动取 key，必须显式传
        params = {
            "model": "qwen-image-2.0-pro",
            "messages": message,
            "api_key": API_KEY
        }

        # 调用Dashscope编辑模型
        response = MultiModalConversation.call(**params)

        url = response['output']['choices'][0]['message']['content'][0]['image']
        return json.dumps({"success": True, "url": url}, ensure_ascii=False)
    except Exception as e:
        print(f"调用编辑模型犯错:{e}")
        return json.dumps({"success": False, "error": f"{e}"}, ensure_ascii=False)


@tool
def merge_image_tool(image_path1: str, image_path2: str, instruction: str) -> str:
    """合并两张图片"
        输入两张本地图片地址路径与合并指令   调用Dashscope的图像编辑模型生成新的URL
        适用于将「衣服/服装/穿搭」与「人物人像」进行合并
        返回JSON字符串: {"success": true, "url":"..."} 或 {"success": false, "error":"..."}
        """
    try:
        with open(image_path1, "rb") as f:
            image_data1 = f.read()
        with open(image_path2, "rb") as f:
            image_data2 = f.read()
        image_data_uri1 = process_image(image_data1)
        image_data_uri2 = process_image(image_data2)

        message = [
            {
                "role": "user",
                "content": [
                    {
                        "image": image_data_uri1
                    },
                    {
                        "image": image_data_uri2
                    },
                    {
                        "text": instruction
                    }
                ]
            }
        ]

        # 构建请求大模型的参数：签名是 messages（复数），且 MultiModalConversation 不会自动取 key，必须显式传
        params = {
            "model": "qwen-image-2.0-pro",
            "messages": message,
            "api_key": API_KEY
        }

        # 调用Dashscope编辑模型
        response = MultiModalConversation.call(**params)

        url = response['output']['choices'][0]['message']['content'][0]['image']
        return json.dumps({"success": True, "url": url}, ensure_ascii=False)
    except Exception as e:
        print(f"调用合并模型犯错:{e}")
        return json.dumps({"success": False, "error": f"{e}"}, ensure_ascii=False)


# 声明一下工具
skills_tools = [edit_image_tool, merge_image_tool]

# Agent 同样改为按需创建：启动阶段不再构建 LangGraph，减少内存与 CPU 占用
_deep_agent = None
_deep_agent_failed = False
_deep_agent_lock = threading.Lock()


def get_agent():
    """按需创建 Agent，只创建一次；失败后不再反复重试"""
    global _deep_agent, _deep_agent_failed
    if _deep_agent_failed:
        raise RuntimeError("Agent 未启用")
    if _deep_agent is None:
        with _deep_agent_lock:
            if _deep_agent is None:
                try:
                    _deep_agent = create_deep_agent(
                        model=llm,
                        tools=skills_tools,
                        skills=["/skills/"],
                        system_prompt=(
                            "你是一个智能图片处理助手，你可以调用两个工具：\n"
                            "- edit_image_tool：编辑单张图片 \n"
                            "- merge_image_tool：合并两张图片（衣服/服装/穿搭 与 人物人像）\n"
                            "如果只提供一张图片路径，必须调用 edit_image_tool；"
                            "如果提供两张图片路径，必须调用 merge_image_tool。\n"
                            "最终的输出格式JSON: {\"success\":true, \"url\":\"字符串类型\"} 或者 {\"success\":false, \"error\":\"字符串类型\"} "
                        )
                    )
                    print("Agent 已经启用")
                except Exception as e:
                    _deep_agent_failed = True
                    print(f"Agent 未启用:{e}")
                    raise RuntimeError("Agent 未启用")
    return _deep_agent


# agent执行函数
def invoke_agent(param : str) -> dict:
    try:
        state = get_agent().invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": param
                    }
                ]
            }
        )

        msg = (state or {}).get("messages") or []
        last = msg[-1] if msg else None
        content = last.content
        obj = json.loads(content)
        return obj
    except Exception as e:
        print(f"执行agent函数出现异常{e}")
        return {"success": False, "error": f"执行agent函数失败{e}"}

def _save_upload_bytes(data: bytes) -> str:
    tmp_dir = tempfile.gettempdir()
    p = os.path.join(tmp_dir, f"aiwear_{uuid.uuid4().hex}.bin")
    with open(p, "wb") as f:
        f.write(data)
    return p


# 操作图片的函数（单图编辑）
def skill_image() -> str:
    try:
        if _deep_agent_failed:
            raise RuntimeError("Agent 未启用")
        instruction = request.form.get("instruction")
        if not instruction:
            raise RuntimeError("缺少 instruction 参数")

        prompt_lines = [
            "你必须调用一个工具，并且只输出 JSON格式",
            "当前任务是编辑单张图片，请调用 edit_image_tool",
            f"instruction: {instruction}"
        ]

        data = request.files["file"].read()
        p = _save_upload_bytes(data)
        prompt_lines.append(f"image_path: {p}")
        out = invoke_agent("\n".join(prompt_lines))
        if not out.get("success") or not out.get("url"):
            raise RuntimeError(out.get("error") or "编辑失败：未返回图片地址")
        return out["url"]
    except Exception as e:
        print(f"执行skill异常{e}")
        raise


# 合并两张图片的函数
def skill_merge_image() -> str:
    try:
        if _deep_agent_failed:
            raise RuntimeError("Agent 未启用")
        instruction = request.form.get("instruction")
        if not instruction:
            raise RuntimeError("缺少 instruction 参数")

        file1 = request.files.get("file1")
        file2 = request.files.get("file2")
        if file1 is None or file2 is None:
            raise RuntimeError("缺少 file1 / file2 参数")

        prompt_lines = [
            "你必须调用一个工具，并且只输出 JSON格式",
            "当前任务是合并两张图片（衣服/服装/穿搭 与 人物人像），请调用 merge_image_tool",
            f"instruction: {instruction}"
        ]

        p1 = _save_upload_bytes(file1.read())
        p2 = _save_upload_bytes(file2.read())
        prompt_lines.append(f"image_path1: {p1}")
        prompt_lines.append(f"image_path2: {p2}")
        out = invoke_agent("\n".join(prompt_lines))
        if not out.get("success") or not out.get("url"):
            raise RuntimeError(out.get("error") or "合并失败：未返回图片地址")
        return out["url"]
    except Exception as e:
        print(f"执行skill合并异常{e}")
        raise

# 定义操作图片（编辑图片）的接口路由
@app.route("/api/skill/image", methods = ["POST"])
def skill_image_api():
    try:
        out = skill_image()
        return jsonify(
            {
                "success": True,
                "url": out,
            }
        ), 200
    except Exception as e:
        print(f"调用skill处理失败{e}")
        return jsonify(
            {
                "success": False,
                "error": str(e)
            }
        ), 500


# 定义合并图片的接口路由
@app.route("/api/skill-image", methods = ["POST"])
def skill_merge_image_api():
    try:
        out = skill_merge_image()
        return jsonify(
            {
                "success": True,
                "url": out,
            }
        ), 200
    except Exception as e:
        print(f"调用skill合并处理失败{e}")
        return jsonify(
            {
                "success": False,
                "error": str(e)
            }
        ), 500

# 服务启动函数
if __name__ == "__main__":
    print("AI服务启动成功！")
    print(f"  PyTorch 线程数 = {_TORCH_THREADS}（可用环境变量 TORCH_NUM_THREADS 调整）")
    print(f"  CLIP 按需加载 = {'开启' if CLIP_ENABLED else '已关闭（CLIP_ENABLED=false）'}")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)