package com.aiwear.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.fasterxml.jackson.annotation.JsonIgnore;
import lombok.Data;
import lombok.ToString;

import java.io.Serializable;
import java.time.LocalDateTime;

// 图片表实体类（files）
@Data
@TableName("files")
public class ImageFile implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    // 上传用户ID
    @TableField("user_id")
    private Long userId;

    // 图片文件名
    @TableField("file_name")
    private String fileName;

    // 图片大小（字节）
    @TableField("file_size")
    private Long fileSize;

    // OSS访问地址
    @TableField("oss_url")
    private String ossUrl;

    // 图片文字描述（大模型生成）
    @TableField("description")
    private String description;

    // 图片类别：clothing/person/other/空串
    @TableField("category")
    private String category;

    // CLIP 向量（JSON 数组文本，512 维，约 7KB）。
    // 三个注解都是必须的，缺一个都会出问题：
    //   @JsonIgnore        —— myImages 直接把实体返回给前端，不挡会把向量塞进列表响应
    //   @ToString.Exclude  —— ApiLogAspect 会 toString 整个响应列表，不排除会把日志刷爆
    //   select = false     —— 普通列表查询不必带上这个大字段；取向量走 selectWithVectorByUserId
    @JsonIgnore
    @ToString.Exclude
    @TableField(value = "`vector`", select = false)
    private String vector;

    // 向量状态：PENDING/READY/FAILED。
    // 注意语义：它只描述「MySQL 里有没有可用的向量」，不代表 Redis 索引的状态
    // ——Redis 是可随时重建的索引，把它的状态写进数据库必然过期失真。
    @TableField("vector_status")
    private String vectorStatus;

    // 向量写入 MySQL 的时间
    @TableField("vector_updated_at")
    private LocalDateTime vectorUpdatedAt;

    // 瞬时字段（不落库）：该图片当前是否已在检索索引里。
    // 只在对账成功时才被赋值，对账失败时保持 null，前端据此不显示角标、避免误报。
    @TableField(exist = false)
    private Boolean indexed;
}

