package com.aiwear.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.aiwear.entity.ImageFile;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

// 图片表mapper
@Mapper
public interface ImageFileMapper extends BaseMapper<ImageFile> {

    // 取出该用户的图片（含向量）。向量字段在实体上是 select = false（列表查询不带），
    // 只有对账/重建索引时才需要它，走这个显式查询。
    @Select("SELECT id, user_id, file_name, file_size, oss_url, description, category, `vector`, vector_status "
            + "FROM files WHERE user_id = #{userId}")
    List<ImageFile> selectWithVectorByUserId(@Param("userId") Long userId);

    // 全库出现过图片的用户 id（启动时逐个对账用）
    @Select("SELECT DISTINCT user_id FROM files")
    List<Long> selectAllUserIds();

    // 库里有图、但没有向量的行（上传时分析失败或历史遗留），启动时限额重算一次
    @Select("SELECT id, user_id, file_name, file_size, oss_url, description, category, `vector`, vector_status "
            + "FROM files WHERE `vector` IS NULL OR `vector` = '' LIMIT #{limit}")
    List<ImageFile> selectRowsMissingVector(@Param("limit") int limit);
}
