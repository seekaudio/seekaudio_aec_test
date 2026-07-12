# =============================================================================
# seekaudio_aec  --  预编译闭源组件 (prebuilt / closed-source component)
#
# 交付给客户的组件目录, 只含:
#   CMakeLists.txt              <- 本文件
#   include/seekaudio_aec.h     <- 引擎公开头文件 (唯一对外接口)
#   lib/libseekaudio_aec.a      <- 加固后的静态库
#
# 客户把整个 seekaudio_aec/ 目录放进自己工程的 components/ 下即可。
#
# 依赖说明: 库链接时用到的 IDF 组件必须声明在 REQUIRES 里, 否则最终链接会出现
# 未解析符号:
#   - esp_timer : 始终需要
#   - esp-dsp   : 仅当这份 .a 是用 ESP-DSP FFT 选项构建时才需要 (默认交付即是);
#                 若是纯 C/float 路径构建, 可删掉 esp-dsp 相关两行。
#
# 注意: 依赖必须挂在 idf_component_register(REQUIRES ...) 上, 不能挂在
# add_prebuilt_library(PRIV_REQUIRES ...) 上 -- 后者内部按组件名直查, 不做
# 托管组件 (espressif__xxx) 的别名解析, 遇到组件管理器安装的 esp-dsp 会在
# set-target/configure 阶段报 "__component_get_property Function invoked
# with incorrect arguments"。REQUIRES 走正常的依赖解析, 两种命名都能处理。
# =============================================================================

# esp-dsp 组件名探测: 组件管理器安装 -> espressif__esp-dsp;
# 手工放在工程 components/ 下 -> esp-dsp。两者取实际存在的那个。
idf_build_get_property(_sa_comps BUILD_COMPONENTS)
if("espressif__esp-dsp" IN_LIST _sa_comps)
    set(_sa_espdsp espressif__esp-dsp)
else()
    set(_sa_espdsp esp-dsp)
endif()

if("espressif__esp-sr" IN_LIST _sa_comps)
    set(_sa_espsr espressif__esp-sr)
else()
    set(_sa_espsr esp-sr)
endif()

idf_component_register(INCLUDE_DIRS "include"
                       REQUIRES esp_timer ${_sa_espdsp} ${_sa_espsr})

# 预编译库: 仅导入 .a, 依赖已在上方 REQUIRES 声明。
add_prebuilt_library(seekaudio_aec_prebuilt
    "${CMAKE_CURRENT_SOURCE_DIR}/lib/libseekaudio_aec.a")

# 用显式链接组把预编译 .a 和 esp-dsp 括进同一个 --start-group 内, 解决 .a 对
# esp-dsp 定点 FFT (dsps_fft2r_sc16_* 等) 的反向引用未解析问题。
# 关键: 组内的库用 $<TARGET_FILE:...> 传"档案文件路径", 而不是 CMake 目标名。
# 传目标名 (idf::xxx) 时 CMake 会对目标去重/重排, 使 --start-group/--end-group
# 标记与库分离而失效; 传路径则标记与档案保持相邻, 组一定成立。
# esp-dsp 在别处被正常链接不受影响 -- 静态库重复出现只是二次扫描, 不会重定义。
target_link_libraries(${COMPONENT_LIB} INTERFACE
    "-Wl,--start-group"
    "$<TARGET_FILE:seekaudio_aec_prebuilt>"
    "$<TARGET_FILE:idf::${_sa_espdsp}>"
    "-Wl,--end-group")
