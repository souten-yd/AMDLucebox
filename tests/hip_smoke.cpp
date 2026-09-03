#include <hip/hip_runtime.h>

#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>

__global__ void add(const float *a, const float *b, float *c, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) c[i] = a[i] + b[i];
}

static bool hip_ok(hipError_t result, const char *operation) {
    if (result == hipSuccess) return true;
    std::fprintf(stderr, "%s: %s\n", operation, hipGetErrorString(result));
    return false;
}

int main(int argc, char **argv) {
    const char *expected = argc > 1 ? argv[1] : "gfx1201";
    hipDeviceProp_t properties{};
    if (!hip_ok(hipGetDeviceProperties(&properties, 0), "hipGetDeviceProperties")) return 1;
    const std::size_t expected_length = std::strlen(expected);
    const bool architecture_matches =
        std::strncmp(properties.gcnArchName, expected, expected_length) == 0 &&
        (properties.gcnArchName[expected_length] == '\0' ||
         properties.gcnArchName[expected_length] == ':');
    if (!architecture_matches) {
        std::fprintf(stderr, "expected %s, got %s\n", expected, properties.gcnArchName);
        return 1;
    }

    constexpr int count = 4096;
    constexpr std::size_t bytes = count * sizeof(float);
    std::vector<float> a(count, 1.25F), b(count, 2.5F), c(count, 0.0F);
    float *da = nullptr, *db = nullptr, *dc = nullptr;
    if (!hip_ok(hipMalloc(&da, bytes), "hipMalloc(a)") ||
        !hip_ok(hipMalloc(&db, bytes), "hipMalloc(b)") ||
        !hip_ok(hipMalloc(&dc, bytes), "hipMalloc(c)")) return 1;
    if (!hip_ok(hipMemcpy(da, a.data(), bytes, hipMemcpyHostToDevice), "copy(a)") ||
        !hip_ok(hipMemcpy(db, b.data(), bytes, hipMemcpyHostToDevice), "copy(b)")) return 1;
    hipLaunchKernelGGL(add, dim3((count + 255) / 256), dim3(256), 0, 0, da, db, dc, count);
    if (!hip_ok(hipGetLastError(), "launch") ||
        !hip_ok(hipMemcpy(c.data(), dc, bytes, hipMemcpyDeviceToHost), "copy(c)")) return 1;
    for (float value : c) {
        if (std::fabs(value - 3.75F) > 1e-6F) {
            std::fputs("vector-add result mismatch\n", stderr);
            return 1;
        }
    }
    if (!hip_ok(hipFree(da), "hipFree(a)") ||
        !hip_ok(hipFree(db), "hipFree(b)") ||
        !hip_ok(hipFree(dc), "hipFree(c)")) return 1;
    std::printf("HIP vector-add passed on %s (%s)\n", properties.name, properties.gcnArchName);
    return 0;
}
