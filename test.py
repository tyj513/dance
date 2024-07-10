import streamlit as st
import os

# 文件上传器
uploaded_file = st.file_uploader("选择一个视频文件", type=["mp4", "mov", "avi"])

if uploaded_file is not None:
    # 获取文件名
    print(uploaded_file)
    file_name = uploaded_file.name
    print(file_name)
    
    # 保存文件到临时位置
    with open(file_name, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # 显示成功消息
    st.success(f"文件 {file_name} 上传成功!")
    
    # 播放视频
    st.video(file_name)
    
    # 清理：删除临时文件
    os.remove(file_name)