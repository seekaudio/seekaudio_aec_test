# ESP-IDF project root for the SeekAudio AEC customer benchmark (ESP32-S3).
#
# The SeekAudio engine is a PREBUILT closed-source component: put the hardened
# static library at components/seekaudio_aec/lib/libseekaudio_aec.a before
# building (see components/seekaudio_aec/lib/PUT_HARDENED_A_HERE.txt).
#
# Build:
#   idf.py set-target esp32s3
#   idf.py build
cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(seekaudio_aec_test)
