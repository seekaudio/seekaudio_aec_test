# main  --  on-device benchmark application component.
#
# Routes all four comparison configs through the shared black-box aec_runner.
# The SeekAudio engine comes from the prebuilt seekaudio_aec component (public
# API only); B1/B2 use esp-sr's esp_aec.h / esp_ns.h / nsnet2.

idf_component_register(
    SRCS
        "aectest.cpp"
        "aec_runner.c"
        "backend_seekaudio.c"
        "fd_aec_backend.cpp"
        "robustness_test.c"
        "bench_port.c"
        "wave_file.cpp"
    INCLUDE_DIRS
        "."
    REQUIRES
        seekaudio_aec
        espressif__esp-sr        # esp_aec.h / esp_aec_nlp.h / esp_ns.h / nsnet2 (B1/B2)
    PRIV_REQUIRES
        esp_timer
        esp-dsp                  # prebuilt .a's fixed-point FFT (dsps_fft2r_sc16_*)
        joltwallet__littlefs
        freertos
        log
        heap
)

target_compile_options(${COMPONENT_LIB} PRIVATE
    -Wno-error=format
    -Wno-error=unused-variable
)

# idf.py -D<VAR>=<VAL> sets a CMake CACHE variable, which is NOT automatically a
# compiler -D. Forward the build-time toggles so e.g.
#   idf.py -DSA_TEST_ROBUSTNESS=0 -DRUN_B2=0 build
# actually reaches the #if in the sources. NOTE: CMake cache vars are sticky --
# to turn a flag back on pass =1 (or `idf.py fullclean`).
foreach(opt
        RUN_A1
        RUN_A2
        RUN_B1
        RUN_B2
        RUN_SA_FULL
        SA_FULL_TYPE
        SA_TEST_ROBUSTNESS
        SA_ROBUST_LEAK_ITERS
        SA_ROBUST_HEAP_TRACE
        SA_ROBUST_FRAMES
        AEC_FILTER_LEN
        SA_CPU_MHZ
        FD_AEC_MODE
        FD_AEC_MODE_B
        FD_NLP_LEVEL
        FD_FILTER_LENGTH
        FD_NSPRO_MODE
        FD_NSNET_MODEL
        B1_BYPASS_NS)
    if(DEFINED ${opt})
        message(STATUS "seekaudio: forwarding ${opt}=${${opt}} to compile definitions")
        target_compile_definitions(${COMPONENT_LIB} PRIVATE ${opt}=${${opt}})
    endif()
endforeach()
