// DroidLens Native Windows 11 Media Foundation Virtual Camera (IMFVirtualCamera)
// Unified 64-bit COM MediaSource + Cross-Session Shared Memory IPC + C Bridge for Python ctypes.

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#define NOMINMAX

#include <windows.h>
#include <unknwn.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mferror.h>
#include <mfobjects.h>
#include <shlwapi.h>
#include <sddl.h>
#include <aclapi.h>
#include <ks.h>
#include <ksproxy.h>
#include <ksmedia.h>
#include <propvarutil.h>
#include <strsafe.h>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <mutex>

#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mfuuid.lib")
#pragma comment(lib, "mf.lib")
#pragma comment(lib, "mfsensorgroup.lib")
#pragma comment(lib, "propsys.lib")
#pragma comment(lib, "shlwapi.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "user32.lib")

// {D819C48B-A324-4B2D-9B8A-7012354A0002}
static const GUID CLSID_DroidLensMediaSource = {
    0xd819c48b, 0xa324, 0x4b2d, {0x9b, 0x8a, 0x70, 0x12, 0x35, 0x4a, 0x00, 0x02}
};
static const wchar_t* kClsidString = L"{D819C48B-A324-4B2D-9B8A-7012354A0002}";
static const wchar_t* kFriendlyName = L"DroidLens Virtual Camera";
static const wchar_t* kSharedFilePath = L"C:\\Users\\Public\\DroidLens_MF_SharedVideo.shm";
static const wchar_t* kGlobalDllDir = L"C:\\ProgramData\\DroidLens";
static const wchar_t* kGlobalDllPath = L"C:\\ProgramData\\DroidLens\\DroidLensMF.dll";

// Ensure forward-compatible definitions if compiling against an older Windows SDK header
#ifndef __IMFVirtualCamera_INTERFACE_DEFINED__
#define __IMFVirtualCamera_INTERFACE_DEFINED__

typedef enum _MFVirtualCameraType {
    MFVirtualCameraType_SoftwareCameraSource = 0
} MFVirtualCameraType;

typedef enum _MFVirtualCameraLifetime {
    MFVirtualCameraLifetime_Session = 0,
    MFVirtualCameraLifetime_System = 1
} MFVirtualCameraLifetime;

typedef enum _MFVirtualCameraAccess {
    MFVirtualCameraAccess_CurrentUser = 0,
    MFVirtualCameraAccess_AllUsers = 1
} MFVirtualCameraAccess;

MIDL_INTERFACE("1C08A864-EF6C-4C75-AF59-5F2D68DA9563")
IMFVirtualCamera : public IMFAttributes {
public:
    virtual HRESULT STDMETHODCALLTYPE AddDeviceSourceInfo(LPCWSTR DeviceSourceInfo) = 0;
    virtual HRESULT STDMETHODCALLTYPE AddProperty(const void* pKey, VARTYPE Type, const BYTE* pbData, ULONG cbData) = 0;
    virtual HRESULT STDMETHODCALLTYPE AddRegistryEntry(LPCWSTR EntryName, LPCWSTR SubkeyPath, DWORD dwRegType, const BYTE* pbData, ULONG cbData) = 0;
    virtual HRESULT STDMETHODCALLTYPE Start(IMFAsyncCallback* pCallback) = 0;
    virtual HRESULT STDMETHODCALLTYPE Stop(void) = 0;
    virtual HRESULT STDMETHODCALLTYPE Remove(void) = 0;
    virtual HRESULT STDMETHODCALLTYPE GetMediaSource(IMFMediaSource** ppMediaSource) = 0;
    virtual HRESULT STDMETHODCALLTYPE SendCameraProperty(REFGUID propertySet, ULONG propertyId, ULONG propertyFlags, void* propertyPayload, ULONG propertyPayloadLength, void* data, ULONG dataLength, ULONG* dataWritten) = 0;
    virtual HRESULT STDMETHODCALLTYPE CreateSyncEvent(REFGUID kseventSet, ULONG kseventId, ULONG kseventFlags, HANDLE eventHandle, IUnknown** cameraSyncObject) = 0;
    virtual HRESULT STDMETHODCALLTYPE CreateSyncSemaphore(REFGUID kseventSet, ULONG kseventId, ULONG kseventFlags, HANDLE semaphoreHandle, LONG semaphoreAdjustment, IUnknown** cameraSyncObject) = 0;
    virtual HRESULT STDMETHODCALLTYPE Shutdown(void) = 0;
};
#endif

// PINNAME_VIDEO_CAPTURE: {FB6C4281-0353-11D1-905F-0000C0CC16BA}
static const GUID kPINNAME_VIDEO_CAPTURE = {
    0xfb6c4281, 0x0353, 0x11d1, {0x90, 0x5f, 0x00, 0x00, 0xc0, 0xcc, 0x16, 0xba}
};

// MF_DEVICESTREAM_FRAMESERVER_SHARED: {1CB3A8E9-B279-41D4-AF97-34A243E68320}
static const GUID kMF_DEVICESTREAM_FRAMESERVER_SHARED = {
    0x1cb3a8e9, 0xb279, 0x41d4, {0xaf, 0x97, 0x34, 0xa2, 0x43, 0xe6, 0x83, 0x20}
};

// MF_DEVICESTREAM_ATTRIBUTE_FRAMESOURCE_TYPES: {17145FD1-1B2B-423C-8001-2B6833ED3588}
static const GUID kMF_DEVICESTREAM_ATTRIBUTE_FRAMESOURCE_TYPES = {
    0x17145fd1, 0x1b2b, 0x423c, {0x80, 0x01, 0x2b, 0x68, 0x33, 0xed, 0x35, 0x88}
};

// MF_VIRTUALCAMERA_PROVIDE_ASSOCIATED_CAMERA_SOURCES: {F0273718-4A4D-4AC5-A15D-305EB5E90667}
static const GUID kMF_VIRTUALCAMERA_PROVIDE_ASSOCIATED_CAMERA_SOURCES = {
    0xf0273718, 0x4a4d, 0x4ac5, {0xa1, 0x5d, 0x30, 0x5e, 0xb5, 0xe9, 0x06, 0x67}
};

// MF_DEVICEMFT_SENSORPROFILE_COLLECTION: {36301627-D285-4715-8222-8C22E277D44F}
static const GUID kMF_DEVICEMFT_SENSORPROFILE_COLLECTION = {
    0x36301627, 0xd285, 0x4715, {0x82, 0x22, 0x8c, 0x22, 0xe2, 0x77, 0xd4, 0x4f}
};

// MFT_TRANSFORM_CLSID_Attribute: {6821C42B-65A4-4E82-99BC-9A88205ECD0C}
static const GUID kMFT_TRANSFORM_CLSID_Attribute = {
    0x6821c42b, 0x65a4, 0x4e82, {0x99, 0xbc, 0x9a, 0x88, 0x20, 0x5e, 0xcd, 0x0c}
};

// KSCAMERAPROFILE_Legacy: {B4F9A30E-6168-4A84-B67D-4C244E6F0C31}
static const GUID kKSCAMERAPROFILE_Legacy = {
    0xb4f9a30e, 0x6168, 0x4a84, {0xb6, 0x7d, 0x4c, 0x24, 0x4e, 0x6f, 0x0c, 0x31}
};

// KSCAMERAPROFILE_HighFrameRate: {C9C3C5B2-7A91-4527-9723-B02B842D32A7}
static const GUID kKSCAMERAPROFILE_HighFrameRate = {
    0xc9c3c5b2, 0x7a91, 0x4527, {0x97, 0x23, 0xb0, 0x2b, 0x84, 0x2d, 0x32, 0xa7}
};

// IID_IKsControl: {28F54685-06FD-11D2-B27A-00A0C9223196}
static const GUID kIID_IKsControl = {
    0x28f54685, 0x06fd, 0x11d2, {0xb2, 0x7a, 0x00, 0xa0, 0xc9, 0x22, 0x31, 0x96}
};

typedef HRESULT(STDAPICALLTYPE* PFN_MFCreateVirtualCamera)(
    MFVirtualCameraType type,
    MFVirtualCameraLifetime lifetime,
    MFVirtualCameraAccess access,
    LPCWSTR friendlyName,
    LPCWSTR sourceId,
    const GUID* categories,
    ULONG categoryCount,
    IMFVirtualCamera** virtualCamera
);

#pragma pack(push, 1)
struct SharedFrameHeader {
    uint32_t magic;       // 0x444C4D46 ('DLMF')
    uint32_t version;     // 1
    uint32_t width;       // e.g. 1280
    uint32_t height;      // e.g. 720
    uint32_t fps;         // e.g. 30
    uint32_t stride;      // width * 4
    uint64_t frame_index; // monotonic frame counter
};
#pragma pack(pop)

static constexpr uint32_t kSharedMagic = 0x444C4D46;
static constexpr uint32_t kDefaultWidth = 1280;
static constexpr uint32_t kDefaultHeight = 720;
static constexpr uint32_t kDefaultFps = 30;
static constexpr size_t kMaxFrameBytes = 1920 * 1080 * 4;
static constexpr size_t kSharedTotalBytes = sizeof(SharedFrameHeader) + kMaxFrameBytes;

static HMODULE g_hModule = nullptr;
static std::atomic<long> g_dllRefCount{0};
static std::atomic<long> g_lastHr{0};

// ============================================================================
// Helper: Cross-session shared memory file mapping & color conversion
// ============================================================================
static HANDLE OpenSharedMemoryFile(bool writeAccess, const uint8_t** ppReadView, uint8_t** ppWriteView) {
    PSECURITY_DESCRIPTOR pSD = nullptr;
    SECURITY_ATTRIBUTES sa{};
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = FALSE;
    if (ConvertStringSecurityDescriptorToSecurityDescriptorW(
            L"D:(A;;GA;;;WD)(A;;GA;;;LS)(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;AU)(A;;GA;;;AC)",
            SDDL_REVISION_1, &pSD, nullptr)) {
        sa.lpSecurityDescriptor = pSD;
    }

    DWORD desiredAccess = writeAccess ? (GENERIC_READ | GENERIC_WRITE) : GENERIC_READ;
    DWORD creationDisp = writeAccess ? OPEN_ALWAYS : OPEN_EXISTING;
    HANDLE hFile = CreateFileW(
        kSharedFilePath,
        desiredAccess,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        sa.lpSecurityDescriptor ? &sa : nullptr,
        creationDisp,
        FILE_ATTRIBUTE_TEMPORARY,
        nullptr
    );

    if (hFile == INVALID_HANDLE_VALUE) {
        if (pSD) LocalFree(pSD);
        return nullptr;
    }

    if (writeAccess) {
        LARGE_INTEGER liSize{};
        liSize.QuadPart = static_cast<LONGLONG>(kSharedTotalBytes);
        SetFilePointerEx(hFile, liSize, nullptr, FILE_BEGIN);
        SetEndOfFile(hFile);
    }

    DWORD flProtect = writeAccess ? PAGE_READWRITE : PAGE_READONLY;
    HANDLE hMap = CreateFileMappingW(
        hFile,
        sa.lpSecurityDescriptor ? &sa : nullptr,
        flProtect,
        0,
        static_cast<DWORD>(kSharedTotalBytes),
        nullptr
    );
    CloseHandle(hFile);
    if (pSD) LocalFree(pSD);

    if (!hMap) return nullptr;

    if (writeAccess && ppWriteView) {
        *ppWriteView = static_cast<uint8_t*>(MapViewOfFile(hMap, FILE_MAP_ALL_ACCESS, 0, 0, kSharedTotalBytes));
        if (!*ppWriteView) {
            CloseHandle(hMap);
            return nullptr;
        }
    } else if (!writeAccess && ppReadView) {
        *ppReadView = static_cast<const uint8_t*>(MapViewOfFile(hMap, FILE_MAP_READ, 0, 0, kSharedTotalBytes));
        if (!*ppReadView) {
            CloseHandle(hMap);
            return nullptr;
        }
    }
    return hMap;
}

static inline void RGB24ToYUY2(int r, int g, int b, BYTE* y, BYTE* u, BYTE* v) {
    *y = static_cast<BYTE>(((66 * r + 129 * g + 25 * b + 128) >> 8) + 16);
    *u = static_cast<BYTE>(((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128);
    *v = static_cast<BYTE>(((112 * r - 94 * g - 18 * b + 128) >> 8) + 128);
}

static inline void RGB24ToY(int r, int g, int b, BYTE* y) {
    *y = static_cast<BYTE>(((66 * r + 129 * g + 25 * b + 128) >> 8) + 16);
}

static void ConvertRGB32ToNV12(const BYTE* input, LONG inputStride, UINT width, UINT height, BYTE* output, LONG outputStride) {
    for (UINT h = 0; h + 1 < height; h += 2) {
        const BYTE* rgb1 = input + h * inputStride;
        const BYTE* rgb2 = input + (h + 1) * inputStride;
        BYTE* y1 = output + h * outputStride;
        BYTE* y2 = output + (h + 1) * outputStride;
        BYTE* uv = output + (h / 2 + height) * outputStride;
        for (UINT w = 0; w + 1 < width; w += 2) {
            RGB24ToYUY2(rgb1[2], rgb1[1], rgb1[0], y1, uv, uv + 1);
            RGB24ToY(rgb1[6], rgb1[5], rgb1[4], y1 + 1);
            RGB24ToYUY2(rgb2[2], rgb2[1], rgb2[0], y2, uv, uv + 1);
            RGB24ToY(rgb2[6], rgb2[5], rgb2[4], y2 + 1);
            rgb1 += 8;
            rgb2 += 8;
            y1 += 2;
            y2 += 2;
            uv += 2;
        }
    }
}

class DroidLensMediaSource;

// ============================================================================
// DroidLensMediaStream (IMFMediaStream2, IMFAttributes, IKsControl)
// ============================================================================
class DroidLensMediaStream : public IMFMediaStream2, public IMFAttributes, public IKsControl {
public:
    DroidLensMediaStream()
        : m_refCount(1), m_parent(nullptr), m_sd(nullptr), m_eventQueue(nullptr),
          m_attrs(nullptr), m_allocator(nullptr), m_state(MF_STREAM_STATE_STOPPED),
          m_format(MFVideoFormat_RGB32), m_width(kDefaultWidth), m_height(kDefaultHeight), m_fps(kDefaultFps) {
        g_dllRefCount.fetch_add(1);
    }

    virtual ~DroidLensMediaStream() {
        Shutdown();
        if (m_allocator) { m_allocator->Release(); m_allocator = nullptr; }
        if (m_sd) { m_sd->Release(); m_sd = nullptr; }
        if (m_attrs) { m_attrs->Release(); m_attrs = nullptr; }
        g_dllRefCount.fetch_sub(1);
    }

    HRESULT Initialize(DroidLensMediaSource* parent, DWORD index) {
        if (!parent) return E_POINTER;
        m_parent = parent;
        m_index = index;

        HRESULT hr = MFCreateAttributes(&m_attrs, 8);
        if (FAILED(hr)) return hr;

        m_attrs->SetGUID(MF_DEVICESTREAM_STREAM_CATEGORY, kPINNAME_VIDEO_CAPTURE);
        m_attrs->SetUINT32(MF_DEVICESTREAM_STREAM_ID, index);
        m_attrs->SetUINT32(kMF_DEVICESTREAM_FRAMESERVER_SHARED, 1);
        m_attrs->SetUINT32(kMF_DEVICESTREAM_ATTRIBUTE_FRAMESOURCE_TYPES, 1); // MFFrameSourceTypes_Color

        hr = MFCreateEventQueue(&m_eventQueue);
        if (FAILED(hr)) return hr;

        IMFMediaType* rgbType = nullptr;
        hr = MFCreateMediaType(&rgbType);
        if (FAILED(hr)) return hr;
        rgbType->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
        rgbType->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_RGB32);
        MFSetAttributeSize(rgbType, MF_MT_FRAME_SIZE, m_width, m_height);
        rgbType->SetUINT32(MF_MT_DEFAULT_STRIDE, m_width * 4);
        rgbType->SetUINT32(MF_MT_SAMPLE_SIZE, m_width * m_height * 4);
        rgbType->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive);
        rgbType->SetUINT32(MF_MT_ALL_SAMPLES_INDEPENDENT, TRUE);
        MFSetAttributeRatio(rgbType, MF_MT_FRAME_RATE, m_fps, 1);
        rgbType->SetUINT32(MF_MT_AVG_BITRATE, m_width * m_height * 4 * 8 * m_fps);
        MFSetAttributeRatio(rgbType, MF_MT_PIXEL_ASPECT_RATIO, 1, 1);

        IMFMediaType* nv12Type = nullptr;
        hr = MFCreateMediaType(&nv12Type);
        if (FAILED(hr)) {
            rgbType->Release();
            return hr;
        }
        nv12Type->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
        nv12Type->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_NV12);
        MFSetAttributeSize(nv12Type, MF_MT_FRAME_SIZE, m_width, m_height);
        nv12Type->SetUINT32(MF_MT_DEFAULT_STRIDE, m_width);
        nv12Type->SetUINT32(MF_MT_SAMPLE_SIZE, (m_width * m_height * 3) / 2);
        nv12Type->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive);
        nv12Type->SetUINT32(MF_MT_ALL_SAMPLES_INDEPENDENT, TRUE);
        MFSetAttributeRatio(nv12Type, MF_MT_FRAME_RATE, m_fps, 1);
        nv12Type->SetUINT32(MF_MT_AVG_BITRATE, static_cast<UINT32>(m_width * 1.5 * m_height * 8 * m_fps));
        MFSetAttributeRatio(nv12Type, MF_MT_PIXEL_ASPECT_RATIO, 1, 1);

        IMFMediaType* types[2] = { rgbType, nv12Type };
        hr = MFCreateStreamDescriptor(index, 2, types, &m_sd);
        if (SUCCEEDED(hr)) {
            IMFMediaTypeHandler* handler = nullptr;
            if (SUCCEEDED(m_sd->GetMediaTypeHandler(&handler))) {
                handler->SetCurrentMediaType(rgbType);
                handler->Release();
            }
        }
        rgbType->Release();
        nv12Type->Release();

        m_hMap = OpenSharedMemoryFile(false, &m_mapView, nullptr);
        return hr;
    }

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IMFMediaEventGenerator || riid == IID_IMFMediaStream || riid == __uuidof(IMFMediaStream2)) {
            *ppv = static_cast<IMFMediaStream2*>(this);
            AddRef();
            return S_OK;
        }
        if (riid == IID_IMFAttributes) {
            *ppv = static_cast<IMFAttributes*>(this);
            AddRef();
            return S_OK;
        }
        if (riid == kIID_IKsControl) {
            *ppv = static_cast<IKsControl*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&m_refCount); }
    STDMETHODIMP_(ULONG) Release() override {
        ULONG c = InterlockedDecrement(&m_refCount);
        if (c == 0) delete this;
        return c;
    }

    // IMFMediaEventGenerator
    STDMETHODIMP GetEvent(DWORD dwFlags, IMFMediaEvent** ppEvent) override {
        if (!ppEvent) return E_POINTER;
        *ppEvent = nullptr;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue) return MF_E_SHUTDOWN;
        return m_eventQueue->GetEvent(dwFlags, ppEvent);
    }
    STDMETHODIMP BeginGetEvent(IMFAsyncCallback* pCallback, IUnknown* punkState) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue) return MF_E_SHUTDOWN;
        return m_eventQueue->BeginGetEvent(pCallback, punkState);
    }
    STDMETHODIMP EndGetEvent(IMFAsyncResult* pResult, IMFMediaEvent** ppEvent) override {
        if (!ppEvent) return E_POINTER;
        *ppEvent = nullptr;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue) return MF_E_SHUTDOWN;
        return m_eventQueue->EndGetEvent(pResult, ppEvent);
    }
    STDMETHODIMP QueueEvent(MediaEventType met, REFGUID guidExtendedType, HRESULT hrStatus, const PROPVARIANT* pvValue) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue) return MF_E_SHUTDOWN;
        return m_eventQueue->QueueEventParamVar(met, guidExtendedType, hrStatus, pvValue);
    }

    // IMFMediaStream
    STDMETHODIMP GetMediaSource(IMFMediaSource** ppMediaSource) override;

    STDMETHODIMP GetStreamDescriptor(IMFStreamDescriptor** ppStreamDescriptor) override {
        if (!ppStreamDescriptor) return E_POINTER;
        *ppStreamDescriptor = nullptr;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_sd) return MF_E_SHUTDOWN;
        *ppStreamDescriptor = m_sd;
        m_sd->AddRef();
        return S_OK;
    }

    STDMETHODIMP RequestSample(IUnknown* pToken) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue) return MF_E_SHUTDOWN;

        IMFSample* pSample = nullptr;
        IMFMediaBuffer* pBuffer = nullptr;
        HRESULT hr = S_OK;

        if (m_allocator) {
            hr = m_allocator->AllocateSample(&pSample);
            if (SUCCEEDED(hr) && pSample) {
                hr = pSample->GetBufferByIndex(0, &pBuffer);
            }
        } else {
            const DWORD cbAlloc = (m_format == MFVideoFormat_NV12)
                ? ((m_width * m_height * 3) / 2)
                : (m_width * m_height * 4);
            hr = MFCreateMemoryBuffer(cbAlloc, &pBuffer);
            if (SUCCEEDED(hr)) {
                hr = MFCreateSample(&pSample);
                if (SUCCEEDED(hr)) {
                    pSample->AddBuffer(pBuffer);
                }
            }
        }

        if (FAILED(hr) || !pSample || !pBuffer) {
            if (pBuffer) pBuffer->Release();
            if (pSample) pSample->Release();
            return FAILED(hr) ? hr : E_FAIL;
        }

        IMF2DBuffer2* pBuffer2D2 = nullptr;
        IMF2DBuffer* pBuffer2D = nullptr;
        BYTE* scanline = nullptr;
        LONG pitch = 0;

        if (SUCCEEDED(pBuffer->QueryInterface(IID_PPV_ARGS(&pBuffer2D2)))) {
            BYTE* start = nullptr;
            DWORD length = 0;
            hr = pBuffer2D2->Lock2DSize(MF2DBuffer_LockFlags_Write, &scanline, &pitch, &start, &length);
            if (SUCCEEDED(hr)) {
                FillSamplePixels(scanline, pitch);
                pBuffer2D2->Unlock2D();
            }
            pBuffer2D2->Release();
        } else if (SUCCEEDED(pBuffer->QueryInterface(IID_PPV_ARGS(&pBuffer2D)))) {
            hr = pBuffer2D->Lock2D(&scanline, &pitch);
            if (SUCCEEDED(hr)) {
                FillSamplePixels(scanline, pitch);
                pBuffer2D->Unlock2D();
            }
            pBuffer2D->Release();
        } else {
            DWORD cbMax = 0;
            hr = pBuffer->Lock(&scanline, &cbMax, nullptr);
            if (SUCCEEDED(hr)) {
                LONG defaultPitch = (m_format == MFVideoFormat_NV12) ? static_cast<LONG>(m_width) : static_cast<LONG>(m_width * 4);
                FillSamplePixels(scanline, defaultPitch);
                pBuffer->Unlock();
                DWORD cbUsed = (m_format == MFVideoFormat_NV12) ? ((m_width * m_height * 3) / 2) : (m_width * m_height * 4);
                pBuffer->SetCurrentLength(cbUsed);
            }
        }

        if (SUCCEEDED(hr)) {
            pSample->SetSampleTime(MFGetSystemTime());
            pSample->SetSampleDuration(333333);
            if (pToken) {
                pSample->SetUnknown(MFSampleExtension_Token, pToken);
            }
            hr = m_eventQueue->QueueEventParamUnk(MEMediaSample, GUID_NULL, S_OK, pSample);
        }

        pBuffer->Release();
        pSample->Release();
        return hr;
    }

    // IMFMediaStream2
    STDMETHODIMP SetStreamState(MF_STREAM_STATE value) override {
        if (m_state == value) return S_OK;
        switch (value) {
        case MF_STREAM_STATE_PAUSED:
            if (m_state != MF_STREAM_STATE_RUNNING) return MF_E_INVALID_STATE_TRANSITION;
            m_state = value;
            return S_OK;
        case MF_STREAM_STATE_RUNNING:
            return Start(nullptr);
        case MF_STREAM_STATE_STOPPED:
            return Stop();
        default:
            return MF_E_INVALID_STATE_TRANSITION;
        }
    }

    STDMETHODIMP GetStreamState(MF_STREAM_STATE* value) override {
        if (!value) return E_POINTER;
        *value = m_state;
        return S_OK;
    }

    HRESULT Start(IMFMediaType* pType) {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue) return MF_E_SHUTDOWN;

        if (pType) {
            pType->GetGUID(MF_MT_SUBTYPE, &m_format);
        }
        if (m_allocator) {
            IMFMediaType* pInitType = pType;
            IMFMediaType* pCurrentType = nullptr;
            if (!pInitType && m_sd) {
                IMFMediaTypeHandler* handler = nullptr;
                if (SUCCEEDED(m_sd->GetMediaTypeHandler(&handler))) {
                    handler->GetCurrentMediaType(&pCurrentType);
                    pInitType = pCurrentType;
                    handler->Release();
                }
            }
            if (pInitType) {
                m_allocator->InitializeSampleAllocator(10, pInitType);
            }
            if (pCurrentType) pCurrentType->Release();
        }

        HRESULT hr = m_eventQueue->QueueEventParamVar(MEStreamStarted, GUID_NULL, S_OK, nullptr);
        if (SUCCEEDED(hr)) {
            m_state = MF_STREAM_STATE_RUNNING;
        }
        return hr;
    }

    HRESULT Stop() {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue) return MF_E_SHUTDOWN;
        if (m_allocator) {
            m_allocator->UninitializeSampleAllocator();
        }
        HRESULT hr = m_eventQueue->QueueEventParamVar(MEStreamStopped, GUID_NULL, S_OK, nullptr);
        m_state = MF_STREAM_STATE_STOPPED;
        return hr;
    }

    MFSampleAllocatorUsage GetAllocatorUsage() const {
        return MFSampleAllocatorUsage_UsesProvidedAllocator;
    }

    HRESULT SetAllocator(IUnknown* pAllocator) {
        if (!pAllocator) return E_POINTER;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (m_allocator) {
            m_allocator->Release();
            m_allocator = nullptr;
        }
        return pAllocator->QueryInterface(IID_PPV_ARGS(&m_allocator));
    }

    HRESULT SetD3DManager(IUnknown* pManager) {
        // Intentionally do not bind D3DManager to m_allocator so samples remain CPU-lockable (2D buffers)
        return S_OK;
    }

    void Shutdown() {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (m_eventQueue) {
            m_eventQueue->Shutdown();
            m_eventQueue->Release();
            m_eventQueue = nullptr;
        }
        if (m_mapView) {
            UnmapViewOfFile(m_mapView);
            m_mapView = nullptr;
        }
        if (m_hMap) {
            CloseHandle(m_hMap);
            m_hMap = nullptr;
        }
        m_parent = nullptr;
    }

    // IKsControl
    STDMETHODIMP_(NTSTATUS) KsProperty(PKSPROPERTY pProperty, ULONG ulPropertyLength, LPVOID pPropertyData, ULONG ulDataLength, ULONG* pBytesReturned) override {
        if (!pProperty || !pBytesReturned) return E_POINTER;
        *pBytesReturned = 0;
        return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
    }
    STDMETHODIMP_(NTSTATUS) KsMethod(PKSMETHOD pMethod, ULONG ulMethodLength, LPVOID pMethodData, ULONG ulDataLength, ULONG* pBytesReturned) override {
        if (!pMethod || !pBytesReturned) return E_POINTER;
        *pBytesReturned = 0;
        return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
    }
    STDMETHODIMP_(NTSTATUS) KsEvent(PKSEVENT pEvent, ULONG ulEventLength, LPVOID pEventData, ULONG ulDataLength, ULONG* pBytesReturned) override {
        if (!pBytesReturned) return E_POINTER;
        *pBytesReturned = 0;
        return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
    }

    // IMFAttributes delegation
    STDMETHODIMP GetItem(REFGUID guidKey, PROPVARIANT* pValue) override { return m_attrs->GetItem(guidKey, pValue); }
    STDMETHODIMP GetItemType(REFGUID guidKey, MF_ATTRIBUTE_TYPE* pType) override { return m_attrs->GetItemType(guidKey, pType); }
    STDMETHODIMP CompareItem(REFGUID guidKey, REFPROPVARIANT Value, BOOL* pbResult) override { return m_attrs->CompareItem(guidKey, Value, pbResult); }
    STDMETHODIMP Compare(IMFAttributes* pTheirs, MF_ATTRIBUTES_MATCH_TYPE MatchType, BOOL* pbResult) override { return m_attrs->Compare(pTheirs, MatchType, pbResult); }
    STDMETHODIMP GetUINT32(REFGUID guidKey, UINT32* punValue) override { return m_attrs->GetUINT32(guidKey, punValue); }
    STDMETHODIMP GetUINT64(REFGUID guidKey, UINT64* punValue) override { return m_attrs->GetUINT64(guidKey, punValue); }
    STDMETHODIMP GetDouble(REFGUID guidKey, double* pfValue) override { return m_attrs->GetDouble(guidKey, pfValue); }
    STDMETHODIMP GetGUID(REFGUID guidKey, GUID* pguidValue) override { return m_attrs->GetGUID(guidKey, pguidValue); }
    STDMETHODIMP GetStringLength(REFGUID guidKey, UINT32* pcchLength) override { return m_attrs->GetStringLength(guidKey, pcchLength); }
    STDMETHODIMP GetString(REFGUID guidKey, LPWSTR pwszValue, UINT32 cchBufSize, UINT32* pcchLength) override { return m_attrs->GetString(guidKey, pwszValue, cchBufSize, pcchLength); }
    STDMETHODIMP GetAllocatedString(REFGUID guidKey, LPWSTR* ppwszValue, UINT32* pcchLength) override { return m_attrs->GetAllocatedString(guidKey, ppwszValue, pcchLength); }
    STDMETHODIMP GetBlobSize(REFGUID guidKey, UINT32* pcbBlobSize) override { return m_attrs->GetBlobSize(guidKey, pcbBlobSize); }
    STDMETHODIMP GetBlob(REFGUID guidKey, UINT8* pBuf, UINT32 cbBufSize, UINT32* pcbBlobSize) override { return m_attrs->GetBlob(guidKey, pBuf, cbBufSize, pcbBlobSize); }
    STDMETHODIMP GetAllocatedBlob(REFGUID guidKey, UINT8** ppBuf, UINT32* pcbSize) override { return m_attrs->GetAllocatedBlob(guidKey, ppBuf, pcbSize); }
    STDMETHODIMP GetUnknown(REFGUID guidKey, REFIID riid, LPVOID* ppv) override { return m_attrs->GetUnknown(guidKey, riid, ppv); }
    STDMETHODIMP SetItem(REFGUID guidKey, REFPROPVARIANT Value) override { return m_attrs->SetItem(guidKey, Value); }
    STDMETHODIMP DeleteItem(REFGUID guidKey) override { return m_attrs->DeleteItem(guidKey); }
    STDMETHODIMP DeleteAllItems() override { return m_attrs->DeleteAllItems(); }
    STDMETHODIMP SetUINT32(REFGUID guidKey, UINT32 unValue) override { return m_attrs->SetUINT32(guidKey, unValue); }
    STDMETHODIMP SetUINT64(REFGUID guidKey, UINT64 unValue) override { return m_attrs->SetUINT64(guidKey, unValue); }
    STDMETHODIMP SetDouble(REFGUID guidKey, double fValue) override { return m_attrs->SetDouble(guidKey, fValue); }
    STDMETHODIMP SetGUID(REFGUID guidKey, REFGUID guidValue) override { return m_attrs->SetGUID(guidKey, guidValue); }
    STDMETHODIMP SetString(REFGUID guidKey, LPCWSTR wszValue) override { return m_attrs->SetString(guidKey, wszValue); }
    STDMETHODIMP SetBlob(REFGUID guidKey, const UINT8* pBuf, UINT32 cbBufSize) override { return m_attrs->SetBlob(guidKey, pBuf, cbBufSize); }
    STDMETHODIMP SetUnknown(REFGUID guidKey, IUnknown* pUnknown) override { return m_attrs->SetUnknown(guidKey, pUnknown); }
    STDMETHODIMP LockStore() override { return m_attrs->LockStore(); }
    STDMETHODIMP UnlockStore() override { return m_attrs->UnlockStore(); }
    STDMETHODIMP GetCount(UINT32* pcItems) override { return m_attrs->GetCount(pcItems); }
    STDMETHODIMP GetItemByIndex(UINT32 unIndex, GUID* pguidKey, PROPVARIANT* pValue) override { return m_attrs->GetItemByIndex(unIndex, pguidKey, pValue); }
    STDMETHODIMP CopyAllItems(IMFAttributes* pDest) override { return m_attrs->CopyAllItems(pDest); }

private:
    void FillSamplePixels(BYTE* pDst, LONG dstPitch) {
        if (!m_mapView) {
            m_hMap = OpenSharedMemoryFile(false, &m_mapView, nullptr);
        }

        const uint8_t* srcBgra = nullptr;
        LONG srcStride = static_cast<LONG>(m_width * 4);

        if (m_mapView) {
            const auto* hdr = reinterpret_cast<const SharedFrameHeader*>(m_mapView);
            if (hdr->magic == kSharedMagic && hdr->frame_index > 0 && hdr->width == m_width && hdr->height == m_height) {
                srcBgra = m_mapView + sizeof(SharedFrameHeader);
            }
        }

        if (m_format == MFVideoFormat_NV12) {
            if (srcBgra) {
                ConvertRGB32ToNV12(srcBgra, srcStride, m_width, m_height, pDst, dstPitch);
            } else {
                // Dark slate standby pattern in NV12 (Y=22, U=129, V=126)
                for (UINT y = 0; y < m_height; ++y) {
                    std::memset(pDst + y * dstPitch, 22, m_width);
                }
                for (UINT y = 0; y < m_height / 2; ++y) {
                    std::memset(pDst + (m_height + y) * dstPitch, 128, m_width);
                }
            }
            return;
        }

        // RGB32 (BGRA)
        if (srcBgra) {
            for (UINT y = 0; y < m_height; ++y) {
                std::memcpy(pDst + y * dstPitch, srcBgra + y * srcStride, m_width * 4);
            }
        } else {
            for (UINT y = 0; y < m_height; ++y) {
                BYTE* row = pDst + y * dstPitch;
                for (UINT x = 0; x < m_width; ++x) {
                    row[x * 4 + 0] = 24;
                    row[x * 4 + 1] = 20;
                    row[x * 4 + 2] = 18;
                    row[x * 4 + 3] = 255;
                }
            }
        }
    }

    ULONG m_refCount;
    std::mutex m_mutex;
    DroidLensMediaSource* m_parent;
    DWORD m_index = 0;
    IMFStreamDescriptor* m_sd;
    IMFMediaEventQueue* m_eventQueue;
    IMFAttributes* m_attrs;
    IMFVideoSampleAllocator* m_allocator;
    MF_STREAM_STATE m_state;
    GUID m_format;
    HANDLE m_hMap = nullptr;
    const uint8_t* m_mapView = nullptr;
    uint32_t m_width;
    uint32_t m_height;
    uint32_t m_fps;
};

// ============================================================================
// DroidLensMediaSource (IMFMediaSourceEx, IMFAttributes, IMFGetService, IMFSampleAllocatorControl, IKsControl)
// ============================================================================
class DroidLensMediaSource :
    public IMFMediaSourceEx,
    public IMFAttributes,
    public IMFGetService,
    public IMFSampleAllocatorControl,
    public IKsControl {
public:
    DroidLensMediaSource()
        : m_refCount(1), m_eventQueue(nullptr), m_pd(nullptr), m_sourceAttrs(nullptr), m_stream(nullptr) {
        g_dllRefCount.fetch_add(1);
    }

    virtual ~DroidLensMediaSource() {
        Shutdown();
        if (m_stream) { m_stream->Release(); m_stream = nullptr; }
        if (m_pd) { m_pd->Release(); m_pd = nullptr; }
        if (m_sourceAttrs) { m_sourceAttrs->Release(); m_sourceAttrs = nullptr; }
        g_dllRefCount.fetch_sub(1);
    }

    HRESULT Initialize(IMFAttributes* pActivateAttrs) {
        HRESULT hr = MFCreateAttributes(&m_sourceAttrs, 8);
        if (FAILED(hr)) return hr;

        if (pActivateAttrs) {
            pActivateAttrs->CopyAllItems(m_sourceAttrs);
        }

        IMFSensorProfileCollection* collection = nullptr;
        hr = MFCreateSensorProfileCollection(&collection);
        if (SUCCEEDED(hr) && collection) {
            IMFSensorProfile* profileLegacy = nullptr;
            if (SUCCEEDED(MFCreateSensorProfile(kKSCAMERAPROFILE_Legacy, 0, nullptr, &profileLegacy))) {
                profileLegacy->AddProfileFilter(0, L"((RES==;FRT<=30,1;SUT==))");
                collection->AddProfile(profileLegacy);
                profileLegacy->Release();
            }
            IMFSensorProfile* profileHfr = nullptr;
            if (SUCCEEDED(MFCreateSensorProfile(kKSCAMERAPROFILE_HighFrameRate, 0, nullptr, &profileHfr))) {
                profileHfr->AddProfileFilter(0, L"((RES==;FRT>=60,1;SUT==))");
                collection->AddProfile(profileHfr);
                profileHfr->Release();
            }
            m_sourceAttrs->SetUnknown(kMF_DEVICEMFT_SENSORPROFILE_COLLECTION, collection);
            collection->Release();
        }

        m_stream = new DroidLensMediaStream();
        hr = m_stream->Initialize(this, 0);
        if (FAILED(hr)) return hr;

        IMFStreamDescriptor* pSD = nullptr;
        hr = m_stream->GetStreamDescriptor(&pSD);
        if (FAILED(hr)) return hr;

        IMFStreamDescriptor* sds[1] = { pSD };
        hr = MFCreatePresentationDescriptor(1, sds, &m_pd);
        pSD->Release();
        if (FAILED(hr)) return hr;

        return MFCreateEventQueue(&m_eventQueue);
    }

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IMFMediaEventGenerator || riid == IID_IMFMediaSource || riid == IID_IMFMediaSourceEx) {
            *ppv = static_cast<IMFMediaSourceEx*>(this);
            AddRef();
            return S_OK;
        }
        if (riid == IID_IMFAttributes) {
            *ppv = static_cast<IMFAttributes*>(this);
            AddRef();
            return S_OK;
        }
        if (riid == IID_IMFGetService) {
            *ppv = static_cast<IMFGetService*>(this);
            AddRef();
            return S_OK;
        }
        if (riid == __uuidof(IMFSampleAllocatorControl)) {
            *ppv = static_cast<IMFSampleAllocatorControl*>(this);
            AddRef();
            return S_OK;
        }
        if (riid == kIID_IKsControl) {
            *ppv = static_cast<IKsControl*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&m_refCount); }
    STDMETHODIMP_(ULONG) Release() override {
        ULONG c = InterlockedDecrement(&m_refCount);
        if (c == 0) delete this;
        return c;
    }

    // IMFGetService
    STDMETHODIMP GetService(REFGUID guidService, REFIID riid, LPVOID* ppvObject) override {
        if (!ppvObject) return E_POINTER;
        *ppvObject = nullptr;
        return MF_E_UNSUPPORTED_SERVICE;
    }

    // IMFSampleAllocatorControl
    STDMETHODIMP SetDefaultAllocator(DWORD dwOutputStreamID, IUnknown* pAllocator) override {
        if (!pAllocator) return E_POINTER;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (dwOutputStreamID != 0 || !m_stream) return E_FAIL;
        return m_stream->SetAllocator(pAllocator);
    }

    STDMETHODIMP GetAllocatorUsage(DWORD dwOutputStreamID, DWORD* pdwInputStreamID, MFSampleAllocatorUsage* peUsage) override {
        if (!pdwInputStreamID || !peUsage) return E_POINTER;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (dwOutputStreamID != 0 || !m_stream) return E_FAIL;
        *pdwInputStreamID = dwOutputStreamID;
        *peUsage = m_stream->GetAllocatorUsage();
        return S_OK;
    }

    // IKsControl
    STDMETHODIMP_(NTSTATUS) KsProperty(PKSPROPERTY pProperty, ULONG ulPropertyLength, LPVOID pPropertyData, ULONG ulDataLength, ULONG* pBytesReturned) override {
        if (!pProperty || !pBytesReturned) return E_POINTER;
        *pBytesReturned = 0;
        return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
    }
    STDMETHODIMP_(NTSTATUS) KsMethod(PKSMETHOD pMethod, ULONG ulMethodLength, LPVOID pMethodData, ULONG ulDataLength, ULONG* pBytesReturned) override {
        if (!pMethod || !pBytesReturned) return E_POINTER;
        *pBytesReturned = 0;
        return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
    }
    STDMETHODIMP_(NTSTATUS) KsEvent(PKSEVENT pEvent, ULONG ulEventLength, LPVOID pEventData, ULONG ulDataLength, ULONG* pBytesReturned) override {
        if (!pBytesReturned) return E_POINTER;
        *pBytesReturned = 0;
        return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND);
    }

    // IMFMediaEventGenerator
    STDMETHODIMP GetEvent(DWORD dwFlags, IMFMediaEvent** ppEvent) override {
        if (!ppEvent) return E_POINTER;
        *ppEvent = nullptr;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue) return MF_E_SHUTDOWN;
        return m_eventQueue->GetEvent(dwFlags, ppEvent);
    }
    STDMETHODIMP BeginGetEvent(IMFAsyncCallback* pCallback, IUnknown* punkState) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue) return MF_E_SHUTDOWN;
        return m_eventQueue->BeginGetEvent(pCallback, punkState);
    }
    STDMETHODIMP EndGetEvent(IMFAsyncResult* pResult, IMFMediaEvent** ppEvent) override {
        if (!ppEvent) return E_POINTER;
        *ppEvent = nullptr;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue) return MF_E_SHUTDOWN;
        return m_eventQueue->EndGetEvent(pResult, ppEvent);
    }
    STDMETHODIMP QueueEvent(MediaEventType met, REFGUID guidExtendedType, HRESULT hrStatus, const PROPVARIANT* pvValue) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue) return MF_E_SHUTDOWN;
        return m_eventQueue->QueueEventParamVar(met, guidExtendedType, hrStatus, pvValue);
    }

    // IMFMediaSource
    STDMETHODIMP GetCharacteristics(DWORD* pdwCharacteristics) override {
        if (!pdwCharacteristics) return E_POINTER;
        *pdwCharacteristics = MFMEDIASOURCE_IS_LIVE;
        return S_OK;
    }

    STDMETHODIMP CreatePresentationDescriptor(IMFPresentationDescriptor** ppPresentationDescriptor) override {
        if (!ppPresentationDescriptor) return E_POINTER;
        *ppPresentationDescriptor = nullptr;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_pd) return MF_E_SHUTDOWN;
        return m_pd->Clone(ppPresentationDescriptor);
    }

    STDMETHODIMP Start(IMFPresentationDescriptor* pPresentationDescriptor, const GUID* pguidTimeFormat, const PROPVARIANT* pvarStartPosition) override {
        if (!pPresentationDescriptor || !pvarStartPosition) return E_POINTER;
        if (pguidTimeFormat && *pguidTimeFormat != GUID_NULL) return E_INVALIDARG;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue || !m_pd || !m_stream) return MF_E_SHUTDOWN;

        DWORD count = 0;
        HRESULT hr = pPresentationDescriptor->GetStreamDescriptorCount(&count);
        if (FAILED(hr) || count != 1) return E_INVALIDARG;

        PROPVARIANT pvTime;
        PropVariantInit(&pvTime);
        pvTime.vt = VT_I8;
        pvTime.hVal.QuadPart = MFGetSystemTime();

        IMFStreamDescriptor* desc = nullptr;
        BOOL selected = FALSE;
        hr = pPresentationDescriptor->GetStreamDescriptorByIndex(0, &selected, &desc);
        if (FAILED(hr)) return hr;

        BOOL thisSelected = FALSE;
        IMFStreamDescriptor* thisDesc = nullptr;
        m_pd->GetStreamDescriptorByIndex(0, &thisSelected, &thisDesc);
        if (thisDesc) thisDesc->Release();

        MF_STREAM_STATE state = MF_STREAM_STATE_STOPPED;
        m_stream->GetStreamState(&state);
        if (thisSelected && state == MF_STREAM_STATE_STOPPED) {
            thisSelected = FALSE;
        } else if (!thisSelected && state != MF_STREAM_STATE_STOPPED) {
            thisSelected = TRUE;
        }

        if (selected != thisSelected) {
            if (selected) {
                m_pd->SelectStream(0);
                m_eventQueue->QueueEventParamUnk(MENewStream, GUID_NULL, S_OK, static_cast<IMFMediaStream2*>(m_stream));

                IMFMediaTypeHandler* handler = nullptr;
                IMFMediaType* type = nullptr;
                if (SUCCEEDED(desc->GetMediaTypeHandler(&handler))) {
                    handler->GetCurrentMediaType(&type);
                    handler->Release();
                }
                hr = m_stream->Start(type);
                if (type) type->Release();
            } else {
                m_pd->DeselectStream(0);
                hr = m_stream->Stop();
            }
        }
        desc->Release();
        if (FAILED(hr)) return hr;

        return m_eventQueue->QueueEventParamVar(MESourceStarted, GUID_NULL, S_OK, &pvTime);
    }

    STDMETHODIMP Stop() override {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue || !m_pd || !m_stream) return MF_E_SHUTDOWN;

        PROPVARIANT pvTime;
        PropVariantInit(&pvTime);
        pvTime.vt = VT_I8;
        pvTime.hVal.QuadPart = MFGetSystemTime();

        m_stream->Stop();
        m_pd->DeselectStream(0);
        return m_eventQueue->QueueEventParamVar(MESourceStopped, GUID_NULL, S_OK, &pvTime);
    }

    STDMETHODIMP Pause() override { return MF_E_INVALID_STATE_TRANSITION; }

    STDMETHODIMP Shutdown() override {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue) return MF_E_SHUTDOWN;
        m_eventQueue->Shutdown();
        m_eventQueue->Release();
        m_eventQueue = nullptr;

        if (m_stream) {
            m_stream->Shutdown();
        }
        if (m_pd) {
            m_pd->Release();
            m_pd = nullptr;
        }
        return S_OK;
    }

    // IMFMediaSourceEx
    STDMETHODIMP GetSourceAttributes(IMFAttributes** ppAttributes) override {
        if (!ppAttributes) return E_POINTER;
        std::lock_guard<std::mutex> lock(m_mutex);
        return QueryInterface(IID_PPV_ARGS(ppAttributes));
    }

    STDMETHODIMP GetStreamAttributes(DWORD dwStreamIdentifier, IMFAttributes** ppAttributes) override {
        if (!ppAttributes) return E_POINTER;
        *ppAttributes = nullptr;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (dwStreamIdentifier != 0 || !m_stream) return E_FAIL;
        return m_stream->QueryInterface(IID_PPV_ARGS(ppAttributes));
    }

    STDMETHODIMP SetD3DManager(IUnknown* pManager) override {
        if (!pManager) return E_POINTER;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_stream) return E_FAIL;
        return m_stream->SetD3DManager(pManager);
    }

    // IMFAttributes delegation
    STDMETHODIMP GetItem(REFGUID guidKey, PROPVARIANT* pValue) override { return m_sourceAttrs->GetItem(guidKey, pValue); }
    STDMETHODIMP GetItemType(REFGUID guidKey, MF_ATTRIBUTE_TYPE* pType) override { return m_sourceAttrs->GetItemType(guidKey, pType); }
    STDMETHODIMP CompareItem(REFGUID guidKey, REFPROPVARIANT Value, BOOL* pbResult) override { return m_sourceAttrs->CompareItem(guidKey, Value, pbResult); }
    STDMETHODIMP Compare(IMFAttributes* pTheirs, MF_ATTRIBUTES_MATCH_TYPE MatchType, BOOL* pbResult) override { return m_sourceAttrs->Compare(pTheirs, MatchType, pbResult); }
    STDMETHODIMP GetUINT32(REFGUID guidKey, UINT32* punValue) override { return m_sourceAttrs->GetUINT32(guidKey, punValue); }
    STDMETHODIMP GetUINT64(REFGUID guidKey, UINT64* punValue) override { return m_sourceAttrs->GetUINT64(guidKey, punValue); }
    STDMETHODIMP GetDouble(REFGUID guidKey, double* pfValue) override { return m_sourceAttrs->GetDouble(guidKey, pfValue); }
    STDMETHODIMP GetGUID(REFGUID guidKey, GUID* pguidValue) override { return m_sourceAttrs->GetGUID(guidKey, pguidValue); }
    STDMETHODIMP GetStringLength(REFGUID guidKey, UINT32* pcchLength) override { return m_sourceAttrs->GetStringLength(guidKey, pcchLength); }
    STDMETHODIMP GetString(REFGUID guidKey, LPWSTR pwszValue, UINT32 cchBufSize, UINT32* pcchLength) override { return m_sourceAttrs->GetString(guidKey, pwszValue, cchBufSize, pcchLength); }
    STDMETHODIMP GetAllocatedString(REFGUID guidKey, LPWSTR* ppwszValue, UINT32* pcchLength) override { return m_sourceAttrs->GetAllocatedString(guidKey, ppwszValue, pcchLength); }
    STDMETHODIMP GetBlobSize(REFGUID guidKey, UINT32* pcbBlobSize) override { return m_sourceAttrs->GetBlobSize(guidKey, pcbBlobSize); }
    STDMETHODIMP GetBlob(REFGUID guidKey, UINT8* pBuf, UINT32 cbBufSize, UINT32* pcbBlobSize) override { return m_sourceAttrs->GetBlob(guidKey, pBuf, cbBufSize, pcbBlobSize); }
    STDMETHODIMP GetAllocatedBlob(REFGUID guidKey, UINT8** ppBuf, UINT32* pcbSize) override { return m_sourceAttrs->GetAllocatedBlob(guidKey, ppBuf, pcbSize); }
    STDMETHODIMP GetUnknown(REFGUID guidKey, REFIID riid, LPVOID* ppv) override { return m_sourceAttrs->GetUnknown(guidKey, riid, ppv); }
    STDMETHODIMP SetItem(REFGUID guidKey, REFPROPVARIANT Value) override { return m_sourceAttrs->SetItem(guidKey, Value); }
    STDMETHODIMP DeleteItem(REFGUID guidKey) override { return m_sourceAttrs->DeleteItem(guidKey); }
    STDMETHODIMP DeleteAllItems() override { return m_sourceAttrs->DeleteAllItems(); }
    STDMETHODIMP SetUINT32(REFGUID guidKey, UINT32 unValue) override { return m_sourceAttrs->SetUINT32(guidKey, unValue); }
    STDMETHODIMP SetUINT64(REFGUID guidKey, UINT64 unValue) override { return m_sourceAttrs->SetUINT64(guidKey, unValue); }
    STDMETHODIMP SetDouble(REFGUID guidKey, double fValue) override { return m_sourceAttrs->SetDouble(guidKey, fValue); }
    STDMETHODIMP SetGUID(REFGUID guidKey, REFGUID guidValue) override { return m_sourceAttrs->SetGUID(guidKey, guidValue); }
    STDMETHODIMP SetString(REFGUID guidKey, LPCWSTR wszValue) override { return m_sourceAttrs->SetString(guidKey, wszValue); }
    STDMETHODIMP SetBlob(REFGUID guidKey, const UINT8* pBuf, UINT32 cbBufSize) override { return m_sourceAttrs->SetBlob(guidKey, pBuf, cbBufSize); }
    STDMETHODIMP SetUnknown(REFGUID guidKey, IUnknown* pUnknown) override { return m_sourceAttrs->SetUnknown(guidKey, pUnknown); }
    STDMETHODIMP LockStore() override { return m_sourceAttrs->LockStore(); }
    STDMETHODIMP UnlockStore() override { return m_sourceAttrs->UnlockStore(); }
    STDMETHODIMP GetCount(UINT32* pcItems) override { return m_sourceAttrs->GetCount(pcItems); }
    STDMETHODIMP GetItemByIndex(UINT32 unIndex, GUID* pguidKey, PROPVARIANT* pValue) override { return m_sourceAttrs->GetItemByIndex(unIndex, pguidKey, pValue); }
    STDMETHODIMP CopyAllItems(IMFAttributes* pDest) override { return m_sourceAttrs->CopyAllItems(pDest); }

private:
    ULONG m_refCount;
    std::mutex m_mutex;
    IMFMediaEventQueue* m_eventQueue;
    IMFPresentationDescriptor* m_pd;
    IMFAttributes* m_sourceAttrs;
    DroidLensMediaStream* m_stream;
};

STDMETHODIMP DroidLensMediaStream::GetMediaSource(IMFMediaSource** ppMediaSource) {
    if (!ppMediaSource) return E_POINTER;
    *ppMediaSource = nullptr;
    if (!m_parent) return MF_E_SHUTDOWN;
    return m_parent->QueryInterface(IID_PPV_ARGS(ppMediaSource));
}

// ============================================================================
// DroidLensActivate (IMFActivate) & DroidLensClassFactory (IClassFactory)
// ============================================================================
class DroidLensActivate : public IMFActivate {
public:
    DroidLensActivate() : m_refCount(1), m_attrs(nullptr), m_source(nullptr) {
        g_dllRefCount.fetch_add(1);
    }

    virtual ~DroidLensActivate() {
        // IMPORTANT: Do NOT call m_source->Shutdown() here!
        // FrameServer releases IMFActivate while continuing to hold and use IMFMediaSource.
        if (m_source) {
            m_source->Release();
            m_source = nullptr;
        }
        if (m_attrs) {
            m_attrs->Release();
            m_attrs = nullptr;
        }
        g_dllRefCount.fetch_sub(1);
    }

    HRESULT Initialize() {
        HRESULT hr = MFCreateAttributes(&m_attrs, 8);
        if (FAILED(hr)) return hr;

        hr = SetUINT32(kMF_VIRTUALCAMERA_PROVIDE_ASSOCIATED_CAMERA_SOURCES, 1);
        if (FAILED(hr)) return hr;

        hr = SetGUID(kMFT_TRANSFORM_CLSID_Attribute, CLSID_DroidLensMediaSource);
        if (FAILED(hr)) return hr;

        m_source = new DroidLensMediaSource();
        return m_source->Initialize(this);
    }

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IMFActivate || riid == IID_IMFAttributes) {
            *ppv = static_cast<IMFActivate*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&m_refCount); }
    STDMETHODIMP_(ULONG) Release() override {
        ULONG c = InterlockedDecrement(&m_refCount);
        if (c == 0) delete this;
        return c;
    }

    // IMFActivate
    STDMETHODIMP ActivateObject(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        *ppv = nullptr;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_source) {
            m_source = new DroidLensMediaSource();
            HRESULT hr = m_source->Initialize(this);
            if (FAILED(hr)) {
                m_source->Release();
                m_source = nullptr;
                return hr;
            }
        }
        return m_source->QueryInterface(riid, ppv);
    }

    STDMETHODIMP ShutdownObject() override {
        // Intentionally no-op per VCamSample reference: FrameServer manages MediaSource lifecycle directly
        return S_OK;
    }

    STDMETHODIMP DetachObject() override {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (m_source) {
            m_source->Release();
            m_source = nullptr;
        }
        return S_OK;
    }

    // IMFAttributes delegation
    STDMETHODIMP GetItem(REFGUID guidKey, PROPVARIANT* pValue) override { return m_attrs->GetItem(guidKey, pValue); }
    STDMETHODIMP GetItemType(REFGUID guidKey, MF_ATTRIBUTE_TYPE* pType) override { return m_attrs->GetItemType(guidKey, pType); }
    STDMETHODIMP CompareItem(REFGUID guidKey, REFPROPVARIANT Value, BOOL* pbResult) override { return m_attrs->CompareItem(guidKey, Value, pbResult); }
    STDMETHODIMP Compare(IMFAttributes* pTheirs, MF_ATTRIBUTES_MATCH_TYPE MatchType, BOOL* pbResult) override { return m_attrs->Compare(pTheirs, MatchType, pbResult); }
    STDMETHODIMP GetUINT32(REFGUID guidKey, UINT32* punValue) override { return m_attrs->GetUINT32(guidKey, punValue); }
    STDMETHODIMP GetUINT64(REFGUID guidKey, UINT64* punValue) override { return m_attrs->GetUINT64(guidKey, punValue); }
    STDMETHODIMP GetDouble(REFGUID guidKey, double* pfValue) override { return m_attrs->GetDouble(guidKey, pfValue); }
    STDMETHODIMP GetGUID(REFGUID guidKey, GUID* pguidValue) override { return m_attrs->GetGUID(guidKey, pguidValue); }
    STDMETHODIMP GetStringLength(REFGUID guidKey, UINT32* pcchLength) override { return m_attrs->GetStringLength(guidKey, pcchLength); }
    STDMETHODIMP GetString(REFGUID guidKey, LPWSTR pwszValue, UINT32 cchBufSize, UINT32* pcchLength) override { return m_attrs->GetString(guidKey, pwszValue, cchBufSize, pcchLength); }
    STDMETHODIMP GetAllocatedString(REFGUID guidKey, LPWSTR* ppwszValue, UINT32* pcchLength) override { return m_attrs->GetAllocatedString(guidKey, ppwszValue, pcchLength); }
    STDMETHODIMP GetBlobSize(REFGUID guidKey, UINT32* pcbBlobSize) override { return m_attrs->GetBlobSize(guidKey, pcbBlobSize); }
    STDMETHODIMP GetBlob(REFGUID guidKey, UINT8* pBuf, UINT32 cbBufSize, UINT32* pcbBlobSize) override { return m_attrs->GetBlob(guidKey, pBuf, cbBufSize, pcbBlobSize); }
    STDMETHODIMP GetAllocatedBlob(REFGUID guidKey, UINT8** ppBuf, UINT32* pcbSize) override { return m_attrs->GetAllocatedBlob(guidKey, ppBuf, pcbSize); }
    STDMETHODIMP GetUnknown(REFGUID guidKey, REFIID riid, LPVOID* ppv) override { return m_attrs->GetUnknown(guidKey, riid, ppv); }
    STDMETHODIMP SetItem(REFGUID guidKey, REFPROPVARIANT Value) override { return m_attrs->SetItem(guidKey, Value); }
    STDMETHODIMP DeleteItem(REFGUID guidKey) override { return m_attrs->DeleteItem(guidKey); }
    STDMETHODIMP DeleteAllItems() override { return m_attrs->DeleteAllItems(); }
    STDMETHODIMP SetUINT32(REFGUID guidKey, UINT32 unValue) override { return m_attrs->SetUINT32(guidKey, unValue); }
    STDMETHODIMP SetUINT64(REFGUID guidKey, UINT64 unValue) override { return m_attrs->SetUINT64(guidKey, unValue); }
    STDMETHODIMP SetDouble(REFGUID guidKey, double fValue) override { return m_attrs->SetDouble(guidKey, fValue); }
    STDMETHODIMP SetGUID(REFGUID guidKey, REFGUID guidValue) override { return m_attrs->SetGUID(guidKey, guidValue); }
    STDMETHODIMP SetString(REFGUID guidKey, LPCWSTR wszValue) override { return m_attrs->SetString(guidKey, wszValue); }
    STDMETHODIMP SetBlob(REFGUID guidKey, const UINT8* pBuf, UINT32 cbBufSize) override { return m_attrs->SetBlob(guidKey, pBuf, cbBufSize); }
    STDMETHODIMP SetUnknown(REFGUID guidKey, IUnknown* pUnknown) override { return m_attrs->SetUnknown(guidKey, pUnknown); }
    STDMETHODIMP LockStore() override { return m_attrs->LockStore(); }
    STDMETHODIMP UnlockStore() override { return m_attrs->UnlockStore(); }
    STDMETHODIMP GetCount(UINT32* pcItems) override { return m_attrs->GetCount(pcItems); }
    STDMETHODIMP GetItemByIndex(UINT32 unIndex, GUID* pguidKey, PROPVARIANT* pValue) override { return m_attrs->GetItemByIndex(unIndex, pguidKey, pValue); }
    STDMETHODIMP CopyAllItems(IMFAttributes* pDest) override { return m_attrs->CopyAllItems(pDest); }

private:
    ULONG m_refCount;
    std::mutex m_mutex;
    IMFAttributes* m_attrs;
    DroidLensMediaSource* m_source;
};

class DroidLensClassFactory : public IClassFactory {
public:
    DroidLensClassFactory() : m_refCount(1) {
        g_dllRefCount.fetch_add(1);
    }
    virtual ~DroidLensClassFactory() {
        g_dllRefCount.fetch_sub(1);
    }

    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IClassFactory) {
            *ppv = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&m_refCount); }
    STDMETHODIMP_(ULONG) Release() override {
        ULONG c = InterlockedDecrement(&m_refCount);
        if (c == 0) delete this;
        return c;
    }

    STDMETHODIMP CreateInstance(IUnknown* pUnkOuter, REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        *ppv = nullptr;
        if (pUnkOuter) return CLASS_E_NOAGGREGATION;

        MFStartup(MF_VERSION);

        auto* act = new DroidLensActivate();
        HRESULT hr = act->Initialize();
        if (SUCCEEDED(hr)) {
            hr = act->QueryInterface(riid, ppv);
        }
        act->Release();
        return hr;
    }

    STDMETHODIMP LockServer(BOOL fLock) override {
        if (fLock) g_dllRefCount.fetch_add(1);
        else g_dllRefCount.fetch_sub(1);
        return S_OK;
    }

private:
    ULONG m_refCount;
};

// ============================================================================
// Producer Controller State (Used by DroidLens.exe via ctypes)
// ============================================================================
static std::mutex g_ctrlMutex;
static IMFVirtualCamera* g_pVirtualCam = nullptr;
static HANDLE g_hSharedMap = nullptr;
static uint8_t* g_pSharedView = nullptr;
static uint64_t g_frameCounter = 0;
static bool g_mfStarted = false;

static PFN_MFCreateVirtualCamera ResolveMFCreateVirtualCamera() {
    HMODULE hMod = LoadLibraryW(L"mfsensorgroup.dll");
    if (!hMod) return nullptr;
    return reinterpret_cast<PFN_MFCreateVirtualCamera>(GetProcAddress(hMod, "MFCreateVirtualCamera"));
}

static void GrantReadExecutePermissions(LPCWSTR path) {
    if (!path || !*path) return;
    PSECURITY_DESCRIPTOR pSD = nullptr;
    // Grant Full Control to SYSTEM & Admins; Read+Execute to Everyone, LocalService, AuthUsers, AllAppPackages
    if (ConvertStringSecurityDescriptorToSecurityDescriptorW(
            L"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1200a9;;;WD)(A;OICI;0x1200a9;;;LS)(A;OICI;0x1200a9;;;AU)(A;OICI;0x1200a9;;;AC)",
            SDDL_REVISION_1, &pSD, nullptr)) {
        PACL pDacl = nullptr;
        BOOL bDaclPresent = FALSE;
        BOOL bDaclDefaulted = FALSE;
        if (GetSecurityDescriptorDacl(pSD, &bDaclPresent, &pDacl, &bDaclDefaulted) && bDaclPresent) {
            SetNamedSecurityInfoW(
                const_cast<LPWSTR>(path),
                SE_FILE_OBJECT,
                DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                nullptr,
                nullptr,
                pDacl,
                nullptr
            );
        }
        LocalFree(pSD);
    }
}

extern "C" {

int __stdcall dl_mf_get_last_hr(void) {
    return static_cast<int>(g_lastHr.load());
}

int __stdcall dl_mf_is_supported(void) {
    PFN_MFCreateVirtualCamera pfn = ResolveMFCreateVirtualCamera();
    if (!pfn) return 0;

    HKEY hKey = nullptr;
    wchar_t subKey[128] = {};
    StringCchPrintfW(subKey, 128, L"CLSID\\%s\\InprocServer32", kClsidString);
    if (RegOpenKeyExW(HKEY_CLASSES_ROOT, subKey, 0, KEY_READ, &hKey) != ERROR_SUCCESS) {
        return 0;
    }
    RegCloseKey(hKey);
    return 1;
}

int __stdcall dl_mf_start(int width, int height, int fps) {
    std::lock_guard<std::mutex> lock(g_ctrlMutex);
    if (g_pVirtualCam != nullptr) return 1;

    PFN_MFCreateVirtualCamera pfnCreate = ResolveMFCreateVirtualCamera();
    if (!pfnCreate) {
        g_lastHr.store( static_cast<long>(E_NOTIMPL) );
        return 0;
    }

    if (!g_mfStarted) {
        HRESULT hrInit = MFStartup(MF_VERSION);
        if (FAILED(hrInit)) {
            g_lastHr.store(hrInit);
            return 0;
        }
        g_mfStarted = true;
    }

    g_hSharedMap = OpenSharedMemoryFile(true, nullptr, &g_pSharedView);
    if (!g_hSharedMap || !g_pSharedView) {
        g_lastHr.store(static_cast<long>(HRESULT_FROM_WIN32(GetLastError())));
        return 0;
    }

    auto* hdr = reinterpret_cast<SharedFrameHeader*>(g_pSharedView);
    hdr->magic = kSharedMagic;
    hdr->version = 1;
    hdr->width = static_cast<uint32_t>(width);
    hdr->height = static_cast<uint32_t>(height);
    hdr->fps = static_cast<uint32_t>(fps > 0 ? fps : 30);
    hdr->stride = static_cast<uint32_t>(width * 4);
    hdr->frame_index = 0;

    HRESULT hr = pfnCreate(
        MFVirtualCameraType_SoftwareCameraSource,
        MFVirtualCameraLifetime_Session,
        MFVirtualCameraAccess_CurrentUser,
        kFriendlyName,
        kClsidString,
        nullptr,
        0,
        &g_pVirtualCam
    );
    if (FAILED(hr) || !g_pVirtualCam) {
        g_lastHr.store(hr);
        UnmapViewOfFile(g_pSharedView);
        g_pSharedView = nullptr;
        CloseHandle(g_hSharedMap);
        g_hSharedMap = nullptr;
        return 0;
    }

    hr = g_pVirtualCam->Start(nullptr);
    if (FAILED(hr)) {
        g_lastHr.store(hr);
        g_pVirtualCam->Release();
        g_pVirtualCam = nullptr;
        UnmapViewOfFile(g_pSharedView);
        g_pSharedView = nullptr;
        CloseHandle(g_hSharedMap);
        g_hSharedMap = nullptr;
        return 0;
    }

    g_lastHr.store(S_OK);
    return 1;
}

int __stdcall dl_mf_send_frame(const uint8_t* bgr_bytes, int width, int height) {
    std::lock_guard<std::mutex> lock(g_ctrlMutex);
    if (!g_pSharedView || !bgr_bytes || width <= 0 || height <= 0) return 0;

    const size_t totalPixels = static_cast<size_t>(width) * static_cast<size_t>(height);
    if (totalPixels * 4 > kMaxFrameBytes) return 0;

    auto* hdr = reinterpret_cast<SharedFrameHeader*>(g_pSharedView);
    uint8_t* dst = g_pSharedView + sizeof(SharedFrameHeader);

    // Convert BGR24 to RGB32 (BGRA)
    for (size_t i = 0; i < totalPixels; ++i) {
        dst[i * 4 + 0] = bgr_bytes[i * 3 + 0];
        dst[i * 4 + 1] = bgr_bytes[i * 3 + 1];
        dst[i * 4 + 2] = bgr_bytes[i * 3 + 2];
        dst[i * 4 + 3] = 255;
    }

    hdr->width = static_cast<uint32_t>(width);
    hdr->height = static_cast<uint32_t>(height);
    hdr->stride = static_cast<uint32_t>(width * 4);
    MemoryBarrier();
    hdr->frame_index = ++g_frameCounter;
    return 1;
}

void __stdcall dl_mf_stop(void) {
    std::lock_guard<std::mutex> lock(g_ctrlMutex);
    if (g_pVirtualCam) {
        g_pVirtualCam->Stop();
        g_pVirtualCam->Remove();
        g_pVirtualCam->Shutdown();
        g_pVirtualCam->Release();
        g_pVirtualCam = nullptr;
    }
    if (g_pSharedView) {
        UnmapViewOfFile(g_pSharedView);
        g_pSharedView = nullptr;
    }
    if (g_hSharedMap) {
        CloseHandle(g_hSharedMap);
        g_hSharedMap = nullptr;
    }
    if (g_mfStarted) {
        MFShutdown();
        g_mfStarted = false;
    }
}

// ============================================================================
// Standard COM DLL Entry Points
// ============================================================================
STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, LPVOID* ppv) {
    if (!ppv) return E_POINTER;
    *ppv = nullptr;
    if (rclsid != CLSID_DroidLensMediaSource) return CLASS_E_CLASSNOTAVAILABLE;

    auto* factory = new DroidLensClassFactory();
    HRESULT hr = factory->QueryInterface(riid, ppv);
    factory->Release();
    return hr;
}

STDAPI DllCanUnloadNow(void) {
    return (g_dllRefCount.load() == 0) ? S_OK : S_FALSE;
}

STDAPI DllRegisterServer(void) {
    wchar_t modulePath[MAX_PATH] = {};
    if (!GetModuleFileNameW(g_hModule, modulePath, MAX_PATH)) {
        return HRESULT_FROM_WIN32(GetLastError());
    }

    // Copy DLL to C:\ProgramData\DroidLens\DroidLensMF.dll so Windows FrameServer
    // (running as NT AUTHORITY\LOCAL SERVICE in Session 0) can always load it
    // even when DroidLens is installed under C:\Users\<user>\AppData\Local\...
    CreateDirectoryW(kGlobalDllDir, nullptr);
    GrantReadExecutePermissions(kGlobalDllDir);

    const wchar_t* registeredPath = modulePath;
    if (_wcsicmp(modulePath, kGlobalDllPath) != 0) {
        if (CopyFileW(modulePath, kGlobalDllPath, FALSE)) {
            registeredPath = kGlobalDllPath;
        } else if (GetFileAttributesW(kGlobalDllPath) != INVALID_FILE_ATTRIBUTES) {
            registeredPath = kGlobalDllPath;
        }
    }

    // Strip Mark-of-the-Web (Zone.Identifier) if present and grant read/execute to FrameServer
    wchar_t zonePath[MAX_PATH + 32] = {};
    StringCchPrintfW(zonePath, _countof(zonePath), L"%s:Zone.Identifier", registeredPath);
    DeleteFileW(zonePath);
    GrantReadExecutePermissions(registeredPath);
    GrantReadExecutePermissions(modulePath);

    wchar_t keyPath[256] = {};
    StringCchPrintfW(keyPath, 256, L"SOFTWARE\\Classes\\CLSID\\%s", kClsidString);

    HKEY hKey = nullptr;
    LSTATUS st = RegCreateKeyExW(HKEY_LOCAL_MACHINE, keyPath, 0, nullptr, 0, KEY_WRITE, nullptr, &hKey, nullptr);
    if (st != ERROR_SUCCESS) return HRESULT_FROM_WIN32(st);
    RegSetValueExW(hKey, nullptr, 0, REG_SZ, reinterpret_cast<const BYTE*>(kFriendlyName),
                   static_cast<DWORD>((wcslen(kFriendlyName) + 1) * sizeof(wchar_t)));
    RegCloseKey(hKey);

    wchar_t inprocPath[256] = {};
    StringCchPrintfW(inprocPath, 256, L"%s\\InprocServer32", keyPath);
    st = RegCreateKeyExW(HKEY_LOCAL_MACHINE, inprocPath, 0, nullptr, 0, KEY_WRITE, nullptr, &hKey, nullptr);
    if (st != ERROR_SUCCESS) return HRESULT_FROM_WIN32(st);

    RegSetValueExW(hKey, nullptr, 0, REG_SZ, reinterpret_cast<const BYTE*>(registeredPath),
                   static_cast<DWORD>((wcslen(registeredPath) + 1) * sizeof(wchar_t)));
    const wchar_t* threading = L"Both";
    RegSetValueExW(hKey, L"ThreadingModel", 0, REG_SZ, reinterpret_cast<const BYTE*>(threading),
                   static_cast<DWORD>((wcslen(threading) + 1) * sizeof(wchar_t)));
    RegCloseKey(hKey);
    return S_OK;
}

STDAPI DllUnregisterServer(void) {
    wchar_t keyPath[256] = {};
    StringCchPrintfW(keyPath, 256, L"SOFTWARE\\Classes\\CLSID\\%s", kClsidString);
    SHDeleteKeyW(HKEY_LOCAL_MACHINE, keyPath);
    DeleteFileW(kGlobalDllPath);
    return S_OK;
}

} // extern "C"

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved) {
    if (ul_reason_for_call == DLL_PROCESS_ATTACH) {
        g_hModule = hModule;
        DisableThreadLibraryCalls(hModule);
    }
    return TRUE;
}
