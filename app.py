import streamlit as st
from rembg import remove
from PIL import Image, ImageFilter
import io
import zipfile

# ================= 1. 页面与状态初始化 =================
st.set_page_config(page_title="AI 抠图工作台 V5", layout="wide", page_icon="🧩")

st.markdown("""
    <style>
    .main {background-color: #f4f6f9;}
    div[data-testid="stExpander"] {background: white; border-radius: 8px; border: 1px solid #ddd;}
    .stButton>button {width: 100%; border-radius: 6px;}
    /* 强调重新生成按钮 */
    button[key^="regen_"] {border: 1px solid #4CAF50; color: #4CAF50;}
    button[key^="regen_"]:hover {background-color: #4CAF50; color: white;}
    /* 强调删除按钮 */
    button[key^="del_"] {border: 1px solid #ff4b4b; color: #ff4b4b;}
    button[key^="del_"]:hover {background-color: #ff4b4b; color: white;}
    </style>
    """, unsafe_allow_html=True)

# === 核心状态管理 ===
# 'processed_cache': 用于存储已经处理好的图片数据
# 结构: { "文件名": image_bytes }
if 'processed_cache' not in st.session_state:
    st.session_state.processed_cache = {}

# 'deleted_files': 记录被删除的文件
if 'deleted_files' not in st.session_state:
    st.session_state.deleted_files = set()

# ================= 2. 图像处理函数 =================
def process_core(image_input, mode_type, threshold, shrink_size):
    """
    执行抠图逻辑，返回 PIL Image 对象
    """
    # 如果传入的是字节流，转为图片对象
    if isinstance(image_input, bytes):
        image = Image.open(io.BytesIO(image_input))
    else:
        image = image_input

    # --- 逻辑分支 ---
    if "硬边" in mode_type:
        # 硬边模式
        result = remove(image)
        r, g, b, a = result.split()
        # 二值化
        a = a.point(lambda x: 255 if x > threshold else 0)
        # 边缘腐蚀
        if shrink_size > 0:
            a = a.filter(ImageFilter.MinFilter(shrink_size * 2 + 1))
        result.putalpha(a)
        return result
        
    elif "发丝" in mode_type:
        # 发丝模式
        return remove(
            image, 
            alpha_matting=True,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=10
        )
    else:
        # 通用模式
        return remove(image)

# ================= 3. 侧边栏 (全局配置区) =================
st.sidebar.title("🎛️ 参数配置区")
st.sidebar.info("💡 提示：这里的设置只会影响**新上传**的图片，或点击**“重新生成”**按钮的图片。")

# 模式选择
current_mode = st.sidebar.radio(
    "1. 选择处理模式",
    ("通用模式 (默认)", "📱 硬边模式 (图标/设备)", "👱‍♀️ 发丝精修 (人像)"),
    index=0
)

# 参数微调
current_erode = 0
current_thresh = 200

if "硬边" in current_mode:
    st.sidebar.markdown("---")
    st.sidebar.write("🔧 **边缘微调 (仅硬边模式)**")
    current_erode = st.sidebar.slider("边缘收缩 (像素)", 0, 5, 1)
    current_thresh = st.sidebar.slider("边缘硬度阈值", 100, 250, 200)

st.sidebar.markdown("---")
if st.sidebar.button("🧹 清空所有缓存", help="如果出现显示异常，点此重置"):
    st.session_state.processed_cache = {}
    st.session_state.deleted_files = set()
    st.rerun()

# ================= 4. 主界面逻辑 =================
st.title("🧩 AI 抠图工作台 V5 (独立控制版)")

uploaded_files = st.file_uploader("📂 上传图片区", 
                                  accept_multiple_files=True, 
                                  type=['png', 'jpg', 'jpeg', 'webp', 'bmp'])

# 顶部下载区占位符
top_bar = st.empty()
final_results_list = []

if uploaded_files:
    # 过滤已删除文件
    active_files = [f for f in uploaded_files if f.name not in st.session_state.deleted_files]
    # 倒序排列（新图在顶）
    active_files = list(reversed(active_files))
    
    if active_files:
        st.write(f"📊 共 {len(active_files)} 张图片")
        
        for file in active_files:
            file_name = file.name
            file_bytes = file.getvalue()
            
            # --- 核心逻辑：检查缓存 ---
            # 只有当缓存里没有这张图时，才进行第一次自动处理
            if file_name not in st.session_state.processed_cache:
                with st.spinner(f"正在初次处理 {file_name}..."):
                    # 使用当前侧边栏的默认配置进行初次处理
                    res_img = process_core(file_bytes, current_mode, current_thresh, current_erode)
                    
                    # 保存结果到缓存
                    buf = io.BytesIO()
                    res_img.save(buf, format="PNG")
                    st.session_state.processed_cache[file_name] = buf.getvalue()

            # 从缓存读取已处理的数据 (无论左侧怎么变，这里都读缓存)
            cached_bytes = st.session_state.processed_cache[file_name]
            
            # 添加到最终打包列表
            final_results_list.append((file_name, cached_bytes))

            # --- 界面渲染 ---
            with st.expander(f"🔹 {file_name}", expanded=True):
                col1, col2, col3 = st.columns([1, 1, 0.8])
                
                # 原图
                with col1:
                    st.image(file, caption="原图", use_container_width=True)
                
                # 结果图 (显示缓存中的图)
                with col2:
                    st.image(cached_bytes, caption="当前结果", use_container_width=True)
                
                # 操作区
                with col3:
                    st.write("#### 🛠️ 调整")
                    
                    # 1. 重新生成按钮 (读取当前左侧配置)
                    regen_label = f"🔄 用左侧【{current_mode.split(' ')[1]}】重算"
                    if st.button(regen_label, key=f"regen_{file_name}"):
                        with st.spinner("正在使用新参数重新计算..."):
                            # 重新计算
                            new_img = process_core(file_bytes, current_mode, current_thresh, current_erode)
                            # 更新缓存
                            buf = io.BytesIO()
                            new_img.save(buf, format="PNG")
                            st.session_state.processed_cache[file_name] = buf.getvalue()
                            st.rerun() # 立即刷新显示

                    st.markdown("---")
                    
                    # 2. 单张下载
                    download_name = file_name.rsplit('.', 1)[0] + "_no_bg.png"
                    st.download_button(
                        label="📥 下载 PNG",
                        data=cached_bytes,
                        file_name=download_name,
                        mime="image/png",
                        key=f"down_{file_name}"
                    )
                    
                    # 3. 删除按钮
                    if st.button("🗑️ 移除此图", key=f"del_{file_name}"):
                        st.session_state.deleted_files.add(file_name)
                        # 可选：同时也从缓存中删除，释放内存
                        if file_name in st.session_state.processed_cache:
                            del st.session_state.processed_cache[file_name]
                        st.rerun()

    # --- 批量下载逻辑 ---
    if final_results_list:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for fname, fbytes in final_results_list:
                new_name = fname.rsplit('.', 1)[0] + "_no_bg.png"
                zf.writestr(new_name, fbytes)
        
        with top_bar.container():
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.download_button(
                    label=f"📦 一键打包下载这 {len(final_results_list)} 张图片 (.zip)",
                    data=zip_buffer.getvalue(),
                    file_name="batch_cutout_v5.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True
                )
            with col_b:
                if st.button("♻️ 撤销删除"):
                    st.session_state.deleted_files = set()
                    st.rerun()

else:
    st.info("👈 请上传图片。首次上传会自动使用当前左侧设置处理，之后可单独调整。")