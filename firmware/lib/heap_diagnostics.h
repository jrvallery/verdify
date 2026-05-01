#pragma once

#include <cstddef>

#ifdef ESP_PLATFORM
#include "esp_heap_caps.h"
#include "esp_system.h"

inline float gh_free_heap_kb() {
    return esp_get_free_heap_size() / 1024.0f;
}

inline float gh_min_free_heap_kb() {
    return esp_get_minimum_free_heap_size() / 1024.0f;
}

inline float gh_largest_free_heap_block_kb() {
    return heap_caps_get_largest_free_block(MALLOC_CAP_8BIT) / 1024.0f;
}
#else
inline float gh_free_heap_kb() { return 0.0f; }
inline float gh_min_free_heap_kb() { return 0.0f; }
inline float gh_largest_free_heap_block_kb() { return 0.0f; }
#endif
