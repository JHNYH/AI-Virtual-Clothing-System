package com.aiwear.service;

import com.aiwear.entity.ImageFile;

// 图片检索索引（Redis）的对账与自愈。
//
// 设计前提：MySQL 是唯一事实来源，Redis 只是「可随时重建的索引」。
// 所以这里的方法一律「失败即放弃」——索引坏了不应该影响业务成败，下一次对账会补上。
public interface ImageIndexService {

    // 把一条图片记录同步进索引。上传事务提交后调用；失败只记日志，靠对账补。
    void indexQuietly(ImageFile imageFile);

    // 对账某个用户：索引里缺的用 MySQL 里存的向量补写，多余/悬空的清掉。
    // 返回 true 表示对账确实跑通了（此时前端的 indexed 标记可信），
    // 返回 false 表示没跑通（Python 不可用等），调用方不应据此判断图片未建索引。
    boolean reconcileUser(Long userId);

    // 启动时对全库用户各对账一次（放到独立线程、吞异常、不阻塞启动）
    void reconcileAllOnStartup();
}
