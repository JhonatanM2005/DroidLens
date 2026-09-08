"""
Test de integración de la Fase 2:
Conecta StreamReceiver con VirtualCameraManager y valida la recepción y
emisión de fotogramas procesados hacia la cámara virtual de Windows.
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pc_client", "src")))
from core.receiver import StreamReceiver
from core.processor import FrameProcessor
from core.virtual_camera import VirtualCameraManager

def test_pipeline(duration_seconds: int = 5):
    print("=" * 60)
    print("      AppCam / DroidLens - Test Pipeline Fase 2")
    print("=" * 60)

    receiver = StreamReceiver(host="127.0.0.1", port=8080)
    processor = FrameProcessor(target_width=1280, target_height=720)
    vcam = VirtualCameraManager(width=1280, height=720, fps=30)

    if not vcam.start():
        print("[ERROR] No se pudo iniciar la camara virtual.")
        return False

    receiver.start()
    print(f"Receptor y Camara Virtual iniciados. Probando durante {duration_seconds}s...")

    start_time = time.time()
    frames_pipelined = 0

    try:
        while time.time() - start_time < duration_seconds:
            frame, meta = receiver.get_latest_frame(timeout=0.05)
            if frame is not None:
                # Procesar frame
                processed = processor.process_frame(frame)
                vcam.send_frame(processed)
                frames_pipelined += 1
            else:
                # Si no hay stream activo, enviar pantalla de espera
                standby = processor.generate_standby_frame("Esperando emision de video...")
                vcam.send_frame(standby)

            stats = receiver.get_stats()
            sys.stdout.write(f"\rFrames procesados: {frames_pipelined} | Conectado: {stats['connected']} | FPS: {stats['fps']} | Latencia: {stats['latency_ms']} ms")
            sys.stdout.flush()
            time.sleep(0.01)

    finally:
        print("\nCerrando componentes...")
        receiver.stop()
        vcam.stop()

    print(f"[OK] Test finalizado. Total frames enviados a virtualcam: {frames_pipelined}")
    return True

if __name__ == "__main__":
    test_pipeline(5)
