// DroidLens Native Windows 11 Media Foundation Virtual Camera (IMFVirtualCamera)
// Unified 64-bit COM MediaSource + Shared Memory IPC + C Bridge for Python ctypes.

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#define NOMINMAX

#include <windows.h>
#include <unknwn.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mferror.h>
#include <shlwapi.h>
#include <strsafe.h>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <mutex>

#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mfuuid.lib")
#pragma comment(lib, "mf.lib")
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
static const wchar_t* kSharedMemName = L"Local\\DroidLens_MF_SharedVideo";

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
    virtual HRESULT STDMETHODCALLTYPE CreateSyncEvent(REFGUID kseventSet, ULONG kseventId, ULONG kseventFlags, HANDLE eventHandle, IMFCameraSyncObject** cameraSyncObject) = 0;
    virtual HRESULT STDMETHODCALLTYPE CreateSyncSemaphore(REFGUID kseventSet, ULONG kseventId, ULONG kseventFlags, HANDLE semaphoreHandle, LONG semaphoreAdjustment, IMFCameraSyncObject** cameraSyncObject) = 0;
    virtual HRESULT STDMETHODCALLTYPE Shutdown(void) = 0;
};
#endif

// MF_DEVICESTREAM_ATTRIBUTE_FRAMESERVER_SHARED: {1CB3A8E9-B279-41D4-AF97-34A243E68320}
static const GUID kMF_DEVICESTREAM_ATTRIBUTE_FRAMESERVER_SHARED = {
    0x1cb3a8e9, 0xb279, 0x41d4, {0xaf, 0x97, 0x34, 0xa2, 0x43, 0xe6, 0x83, 0x20}
};

// MF_VIRTUALCAMERA_PROVIDE_ASSOCIATED_CAMERA_SOURCES: {F0273718-4A4D-4AC5-A15D-305EB5E90667}
static const GUID kMF_VIRTUALCAMERA_PROVIDE_ASSOCIATED_CAMERA_SOURCES = {
    0xf0273718, 0x4a4d, 0x4ac5, {0xa1, 0x5d, 0x30, 0x5e, 0xb5, 0xe9, 0x06, 0x67}
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
static constexpr size_t kMaxFrameBytes = 1920 * 1080 * 4;
static constexpr size_t kSharedTotalBytes = sizeof(SharedFrameHeader) + kMaxFrameBytes;

static HMODULE g_hModule = nullptr;
static std::atomic<long> g_dllRefCount{0};

// ============================================================================
// Forward declarations
// ============================================================================
class DroidLensMediaSource;

// ============================================================================
// DroidLensMediaStream (IMFMediaStream)
// ============================================================================
class DroidLensMediaStream : public IMFMediaStream {
public:
    DroidLensMediaStream(DroidLensMediaSource* parent, IMFStreamDescriptor* sd, uint32_t width, uint32_t height, uint32_t fps)
        : m_refCount(1), m_parent(parent), m_sd(sd), m_width(width), m_height(height), m_fps(fps) {
        g_dllRefCount.fetch_add(1);
        if (m_sd) m_sd->AddRef();
        MFCreateEventQueue(&m_eventQueue);
        m_hMap = OpenFileMappingW(FILE_MAP_READ, FALSE, kSharedMemName);
        if (m_hMap) {
            m_mapView = static_cast<const uint8_t*>(MapViewOfFile(m_hMap, FILE_MAP_READ, 0, 0, kSharedTotalBytes));
        }
    }

    virtual ~DroidLensMediaStream() {
        Shutdown();
        if (m_sd) m_sd->Release();
        g_dllRefCount.fetch_sub(1);
    }

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IMFMediaEventGenerator || riid == IID_IMFMediaStream) {
            *ppv = static_cast<IMFMediaStream*>(this);
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
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_sd) return MF_E_SHUTDOWN;
        *ppStreamDescriptor = m_sd;
        m_sd->AddRef();
        return S_OK;
    }

    STDMETHODIMP RequestSample(IUnknown* pToken) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue) return MF_E_SHUTDOWN;

        const DWORD cbFrame = m_width * m_height * 4;
        IMFMediaBuffer* pBuffer = nullptr;
        HRESULT hr = MFCreateMemoryBuffer(cbFrame, &pBuffer);
        if (FAILED(hr)) return hr;

        BYTE* pDst = nullptr;
        hr = pBuffer->Lock(&pDst, nullptr, nullptr);
        if (SUCCEEDED(hr)) {
            FillFrameBuffer(pDst, cbFrame);
            pBuffer->Unlock();
            pBuffer->SetCurrentLength(cbFrame);
        }

        IMFSample* pSample = nullptr;
        hr = MFCreateSample(&pSample);
        if (SUCCEEDED(hr)) {
            pSample->AddBuffer(pBuffer);
            LONGLONG now100ns = MFGetSystemTime();
            LONGLONG dur100ns = (m_fps > 0) ? (10000000LL / m_fps) : 333333LL;
            pSample->SetSampleTime(now100ns);
            pSample->SetSampleDuration(dur100ns);
            if (pToken) {
                pSample->SetUnknown(MFSampleExtension_Token, pToken);
            }
            m_eventQueue->QueueEventParamUnk(MEMediaSample, GUID_NULL, S_OK, pSample);
            pSample->Release();
        }
        pBuffer->Release();
        return hr;
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
    }

private:
    void FillFrameBuffer(BYTE* pDst, DWORD cbFrame) {
        if (!m_mapView) {
            m_hMap = OpenFileMappingW(FILE_MAP_READ, FALSE, kSharedMemName);
            if (m_hMap) {
                m_mapView = static_cast<const uint8_t*>(MapViewOfFile(m_hMap, FILE_MAP_READ, 0, 0, kSharedTotalBytes));
            }
        }

        if (m_mapView) {
            const auto* hdr = reinterpret_cast<const SharedFrameHeader*>(m_mapView);
            if (hdr->magic == kSharedMagic && hdr->frame_index > 0 && hdr->width == m_width && hdr->height == m_height) {
                const uint8_t* srcPixels = m_mapView + sizeof(SharedFrameHeader);
                std::memcpy(pDst, srcPixels, cbFrame);
                return;
            }
        }

        // Default dark slate standby pattern (BGRA: 24, 20, 18, 255)
        for (DWORD i = 0; i + 3 < cbFrame; i += 4) {
            pDst[i + 0] = 24;
            pDst[i + 1] = 20;
            pDst[i + 2] = 18;
            pDst[i + 3] = 255;
        }
    }

    ULONG m_refCount;
    std::mutex m_mutex;
    DroidLensMediaSource* m_parent;
    IMFStreamDescriptor* m_sd;
    IMFMediaEventQueue* m_eventQueue = nullptr;
    HANDLE m_hMap = nullptr;
    const uint8_t* m_mapView = nullptr;
    uint32_t m_width;
    uint32_t m_height;
    uint32_t m_fps;
};

// ============================================================================
// DroidLensMediaSource (IMFMediaSourceEx, IMFGetService)
// ============================================================================
class DroidLensMediaSource : public IMFMediaSourceEx, public IMFGetService {
public:
    DroidLensMediaSource() : m_refCount(1) {
        g_dllRefCount.fetch_add(1);
        MFCreateEventQueue(&m_eventQueue);
        MFCreateAttributes(&m_sourceAttrs, 4);
        if (m_sourceAttrs) {
            m_sourceAttrs->SetUINT32(kMF_VIRTUALCAMERA_PROVIDE_ASSOCIATED_CAMERA_SOURCES, 1);
        }
        InitializePresentationDescriptor(1280, 720, 30);
    }

    virtual ~DroidLensMediaSource() {
        Shutdown();
        if (m_pd) m_pd->Release();
        if (m_streamAttrs) m_streamAttrs->Release();
        if (m_sourceAttrs) m_sourceAttrs->Release();
        g_dllRefCount.fetch_sub(1);
    }

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IMFMediaEventGenerator || riid == IID_IMFMediaSource || riid == IID_IMFMediaSourceEx) {
            *ppv = static_cast<IMFMediaSourceEx*>(this);
            AddRef();
            return S_OK;
        }
        if (riid == IID_IMFGetService) {
            *ppv = static_cast<IMFGetService*>(this);
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

    // IMFMediaEventGenerator
    STDMETHODIMP GetEvent(DWORD dwFlags, IMFMediaEvent** ppEvent) override {
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
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_pd) return MF_E_SHUTDOWN;
        return m_pd->Clone(ppPresentationDescriptor);
    }

    STDMETHODIMP Start(IMFPresentationDescriptor* pPresentationDescriptor, const GUID* pguidTimeFormat, const PROPVARIANT* pvarStartPosition) override {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue || !m_pd) return MF_E_SHUTDOWN;

        BOOL fSelected = FALSE;
        IMFStreamDescriptor* pSD = nullptr;
        HRESULT hr = m_pd->GetStreamDescriptorByIndex(0, &fSelected, &pSD);
        if (FAILED(hr)) return hr;

        MediaEventType met = MENewStream;
        if (m_stream) {
            met = MEUpdatedStream;
        } else {
            m_stream = new DroidLensMediaStream(this, pSD, 1280, 720, 30);
        }
        pSD->Release();

        m_eventQueue->QueueEventParamUnk(met, GUID_NULL, S_OK, static_cast<IMFMediaStream*>(m_stream));

        PROPVARIANT varEmpty;
        PropVariantInit(&varEmpty);
        m_eventQueue->QueueEventParamVar(MESourceStarted, GUID_NULL, S_OK, &varEmpty);
        m_stream->QueueEvent(MEStreamStarted, GUID_NULL, S_OK, &varEmpty);
        return S_OK;
    }

    STDMETHODIMP Stop() override {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_eventQueue) return MF_E_SHUTDOWN;
        PROPVARIANT varEmpty;
        PropVariantInit(&varEmpty);
        if (m_stream) {
            m_stream->QueueEvent(MEStreamStopped, GUID_NULL, S_OK, &varEmpty);
        }
        return m_eventQueue->QueueEventParamVar(MESourceStopped, GUID_NULL, S_OK, &varEmpty);
    }

    STDMETHODIMP Pause() override { return MF_E_INVALID_STATE_TRANSITION; }

    STDMETHODIMP Shutdown() override {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (m_stream) {
            m_stream->Shutdown();
            m_stream->Release();
            m_stream = nullptr;
        }
        if (m_eventQueue) {
            m_eventQueue->Shutdown();
            m_eventQueue->Release();
            m_eventQueue = nullptr;
        }
        return S_OK;
    }

    // IMFMediaSourceEx
    STDMETHODIMP GetSourceAttributes(IMFAttributes** ppAttributes) override {
        if (!ppAttributes) return E_POINTER;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_sourceAttrs) return MF_E_SHUTDOWN;
        *ppAttributes = m_sourceAttrs;
        m_sourceAttrs->AddRef();
        return S_OK;
    }

    STDMETHODIMP GetStreamAttributes(DWORD dwStreamIdentifier, IMFAttributes** ppAttributes) override {
        if (!ppAttributes) return E_POINTER;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_streamAttrs) return MF_E_SHUTDOWN;
        *ppAttributes = m_streamAttrs;
        m_streamAttrs->AddRef();
        return S_OK;
    }

    STDMETHODIMP SetD3DManager(IUnknown* pManager) override { return S_OK; }

private:
    void InitializePresentationDescriptor(uint32_t width, uint32_t height, uint32_t fps) {
        IMFMediaType* pType = nullptr;
        if (FAILED(MFCreateMediaType(&pType))) return;
        pType->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
        pType->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_RGB32);
        pType->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive);
        pType->SetUINT32(MF_MT_ALL_SAMPLES_INDEPENDENT, TRUE);
        MFSetAttributeSize(pType, MF_MT_FRAME_SIZE, width, height);
        MFSetAttributeRatio(pType, MF_MT_FRAME_RATE, fps, 1);
        MFSetAttributeRatio(pType, MF_MT_PIXEL_ASPECT_RATIO, 1, 1);
        pType->SetUINT32(MF_MT_DEFAULT_STRIDE, width * 4);
        pType->SetUINT32(MF_MT_SAMPLE_SIZE, width * height * 4);

        IMFStreamDescriptor* pSD = nullptr;
        IMFMediaType* types[1] = { pType };
        if (SUCCEEDED(MFCreateStreamDescriptor(0, 1, types, &pSD))) {
            IMFMediaTypeHandler* pHandler = nullptr;
            if (SUCCEEDED(pSD->GetMediaTypeHandler(&pHandler))) {
                pHandler->SetCurrentMediaType(pType);
                pHandler->Release();
            }
            MFCreateAttributes(&m_streamAttrs, 4);
            if (m_streamAttrs) {
                m_streamAttrs->SetUINT32(kMF_DEVICESTREAM_ATTRIBUTE_FRAMESERVER_SHARED, 1);
                m_streamAttrs->SetGUID(MF_DEVICESTREAM_STREAM_CATEGORY, PINNAME_VIDEO_CAPTURE);
                m_streamAttrs->SetUINT32(MF_DEVICESTREAM_STREAM_ID, 0);
            }
            IMFStreamDescriptor* sds[1] = { pSD };
            if (SUCCEEDED(MFCreatePresentationDescriptor(1, sds, &m_pd))) {
                m_pd->SelectStream(0);
            }
            pSD->Release();
        }
        pType->Release();
    }

    ULONG m_refCount;
    std::mutex m_mutex;
    IMFMediaEventQueue* m_eventQueue = nullptr;
    IMFPresentationDescriptor* m_pd = nullptr;
    IMFAttributes* m_sourceAttrs = nullptr;
    IMFAttributes* m_streamAttrs = nullptr;
    DroidLensMediaStream* m_stream = nullptr;
};

STDMETHODIMP DroidLensMediaStream::GetMediaSource(IMFMediaSource** ppMediaSource) {
    if (!ppMediaSource) return E_POINTER;
    if (!m_parent) return MF_E_SHUTDOWN;
    *ppMediaSource = static_cast<IMFMediaSourceEx*>(m_parent);
    (*ppMediaSource)->AddRef();
    return S_OK;
}

// ============================================================================
// DroidLensActivate & ClassFactory (IMFActivate + IClassFactory)
// ============================================================================
class DroidLensActivate : public IMFActivate, public IClassFactory {
public:
    DroidLensActivate() : m_refCount(1) {
        g_dllRefCount.fetch_add(1);
        MFCreateAttributes(&m_attrs, 8);
    }
    virtual ~DroidLensActivate() {
        ShutdownObject();
        if (m_attrs) m_attrs->Release();
        g_dllRefCount.fetch_sub(1);
    }

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IMFActivate || riid == IID_IMFAttributes) {
            *ppv = static_cast<IMFActivate*>(this);
            AddRef();
            return S_OK;
        }
        if (riid == IID_IClassFactory) {
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

    // IClassFactory
    STDMETHODIMP CreateInstance(IUnknown* pUnkOuter, REFIID riid, void** ppv) override {
        if (pUnkOuter) return CLASS_E_NOAGGREGATION;
        if (!ppv) return E_POINTER;
        if (riid == IID_IMFActivate) {
            return QueryInterface(riid, ppv);
        }
        auto* src = new DroidLensMediaSource();
        HRESULT hr = src->QueryInterface(riid, ppv);
        src->Release();
        return hr;
    }
    STDMETHODIMP LockServer(BOOL fLock) override {
        if (fLock) g_dllRefCount.fetch_add(1);
        else g_dllRefCount.fetch_sub(1);
        return S_OK;
    }

    // IMFActivate
    STDMETHODIMP ActivateObject(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_source) {
            m_source = new DroidLensMediaSource();
        }
        return m_source->QueryInterface(riid, ppv);
    }
    STDMETHODIMP ShutdownObject() override {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (m_source) {
            m_source->Shutdown();
            m_source->Release();
            m_source = nullptr;
        }
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
    IMFAttributes* m_attrs = nullptr;
    DroidLensMediaSource* m_source = nullptr;
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

extern "C" {

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
    if (!pfnCreate) return 0;

    if (!g_mfStarted) {
        if (FAILED(MFStartup(MF_VERSION))) return 0;
        g_mfStarted = true;
    }

    g_hSharedMap = CreateFileMappingW(
        INVALID_HANDLE_VALUE,
        nullptr,
        PAGE_READWRITE,
        0,
        static_cast<DWORD>(kSharedTotalBytes),
        kSharedMemName
    );
    if (!g_hSharedMap) return 0;

    g_pSharedView = static_cast<uint8_t*>(MapViewOfFile(g_hSharedMap, FILE_MAP_ALL_ACCESS, 0, 0, kSharedTotalBytes));
    if (!g_pSharedView) {
        CloseHandle(g_hSharedMap);
        g_hSharedMap = nullptr;
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
        UnmapViewOfFile(g_pSharedView);
        g_pSharedView = nullptr;
        CloseHandle(g_hSharedMap);
        g_hSharedMap = nullptr;
        return 0;
    }

    hr = g_pVirtualCam->Start(nullptr);
    if (FAILED(hr)) {
        g_pVirtualCam->Release();
        g_pVirtualCam = nullptr;
        UnmapViewOfFile(g_pSharedView);
        g_pSharedView = nullptr;
        CloseHandle(g_hSharedMap);
        g_hSharedMap = nullptr;
        return 0;
    }

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
    if (rclsid != CLSID_DroidLensMediaSource) return CLASS_E_CLASSNOTAVAILABLE;

    auto* factory = new DroidLensActivate();
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

    RegSetValueExW(hKey, nullptr, 0, REG_SZ, reinterpret_cast<const BYTE*>(modulePath),
                   static_cast<DWORD>((wcslen(modulePath) + 1) * sizeof(wchar_t)));
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
