"""
Simulador de la App de Android para DroidLens.
Abre un servidor TCP en 127.0.0.1:8080 y emite fotogramas JPEG empaquetados
con la cabecera binaria APCM a 30 FPS, emulando exactamente la transmisión
del teléfono por cable USB.
"""

import socket
import time
import math
import cv2
import numpy as np

# Importar protocolo
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pc_client", "src")))
from core.protocol import pack_frame

HOST = "127.0.0.1"
PORT = 8080
WIDTH = 1280
HEIGHT = 720
TARGET_FPS = 30

def generate_mock_camera_frame(frame_idx: int) -> np.ndarray:
    """Genera una imagen que simula la cámara del celular con video animado."""
    t = frame_idx * 0.04
    # Fondo degradado
    frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    frame[:, :, 0] = int((math.sin(t) + 1) * 30 + 30)       # Azul
    frame[:, :, 1] = int((math.sin(t + 1) + 1) * 20 + 20)   # Verde
    frame[:, :, 2] = int((math.sin(t + 2) + 1) * 35 + 35)   # Rojo

    # Simular una "persona" en el centro (cabeza y hombros)
    cx, cy = WIDTH // 2, HEIGHT // 2 + 30
    sway_x = int(cx + 25 * math.sin(t * 0.8))

    # Hombros
    cv2.ellipse(frame, (sway_x, cy + 180), (190, 100), 0, 0, 360, (70, 70, 90), -1)
    # Cabeza
    cv2.circle(frame, (sway_x, cy), 95, (190, 160, 140), -1)
    # Ojos
    eye_offset = int(5 * math.sin(t * 1.5))
    cv2.circle(frame, (sway_x - 35, cy - 15), 10, (20, 20, 20), -1)
    cv2.circle(frame, (sway_x + 35, cy - 15), 10, (20, 20, 20), -1)
    # Sonrisa
    cv2.ellipse(frame, (sway_x, cy + 30), (35, 20), 0, 0, 180, (40, 40, 40), 3)

    # Marco de la interfaz del celular
    cv2.rectangle(frame, (30, 30), (WIDTH - 30, HEIGHT - 30), (255, 140, 0), 2)
    cv2.putText(frame, "SIMULADOR ANDROID - DroidLens", (50, 70),
                cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 2)
    
    time_str = time.strftime("%H:%M:%S")
    cv2.putText(frame, f"USB Stream :8080 | Frame #{frame_idx} | {time_str}", (50, 110),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 180), 2)

    return frame

def run_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"[Simulador Android] Escuchando en {HOST}:{PORT}...")
    print("Inicia el receptor de PC para comenzar la transmision.")

    try:
        while True:
            client, addr = server.accept()
            print(f"[Simulador Android] Cliente PC conectado desde {addr}")
            frame_id = 0
            frame_interval = 1.0 / TARGET_FPS

            try:
                while True:
                    start_loop = time.time()
                    # Generar frame y codificar a JPEG
                    raw_frame = generate_mock_camera_frame(frame_id)
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
                    _, jpeg_bytes = cv2.imencode('.jpg', raw_frame, encode_param)

                    # Empaquetar con cabecera APCM
                    timestamp_ms = int(time.time() * 1000)
                    packet = pack_frame(frame_id, timestamp_ms, jpeg_bytes.tobytes())

                    # Enviar por socket TCP
                    client.sendall(packet)
                    frame_id += 1

                    # Mantener 30 FPS
                    elapsed = time.time() - start_loop
                    sleep_time = frame_interval - elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)

            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                print("[Simulador Android] Cliente PC desconectado. Esperando nueva conexion...")
            finally:
                client.close()

    except KeyboardInterrupt:
        print("\n[Simulador Android] Servidor detenido.")
    finally:
        server.close()

if __name__ == "__main__":
    run_server()
