"""
Prueba sintética de la cámara virtual DirectShow (UnityCapture).
Genera un patrón de prueba dinámico con contador de FPS, tiempo en vivo
y un gráfico animado para verificar que Windows y las apps de videollamada
(Zoom, Meet, Teams, app Cámara de Windows) reciben el video fluido.
"""

import time
import math
import sys
import numpy as np
import cv2
import pyvirtualcam

WIDTH = 1280
HEIGHT = 720
TARGET_FPS = 30

def create_test_pattern(frame_idx: int, width: int, height: int, current_fps: float) -> np.ndarray:
    """Genera un fotograma sintético dinámico en formato BGR."""
    # Fondo con degradado animado
    t = frame_idx * 0.03
    r = int((math.sin(t) + 1) * 20 + 20)
    g = int((math.sin(t + 2) + 1) * 25 + 25)
    b = int((math.sin(t + 4) + 1) * 40 + 40)
    
    frame = np.full((height, width, 3), (b, g, r), dtype=np.uint8)
    
    # Dibujar cuadrícula tenue
    grid_size = 40
    for x in range(0, width, grid_size):
        cv2.line(frame, (x, 0), (x, height), (b + 15, g + 15, r + 15), 1)
    for y in range(0, height, grid_size):
        cv2.line(frame, (0, y), (width, y), (b + 15, g + 15, r + 15), 1)
        
    # Elemento animado: Círculo orbitando en el centro
    center_x = width // 2
    center_y = height // 2
    orbit_radius = 160
    circle_x = int(center_x + orbit_radius * math.cos(t * 1.5))
    circle_y = int(center_y + orbit_radius * math.sin(t * 1.5))
    
    # Círculo central estático
    cv2.circle(frame, (center_x, center_y), orbit_radius, (80, 80, 80), 2)
    # Círculo orbitante
    cv2.circle(frame, (circle_x, circle_y), 32, (0, 220, 255), -1)
    cv2.circle(frame, (circle_x, circle_y), 34, (255, 255, 255), 2)
    
    # Cuadro informativo en el centro
    box_w, box_h = 560, 220
    x1, y1 = center_x - box_w // 2, center_y - box_h // 2
    cv2.rectangle(frame, (x1, y1), (x1 + box_w, y1 + box_h), (20, 20, 20), -1)
    cv2.rectangle(frame, (x1, y1), (x1 + box_w, y1 + box_h), (0, 200, 100), 2)
    
    # Textos informativos
    timestamp_str = time.strftime("%H:%M:%S")
    cv2.putText(frame, "AppCam - Camara Virtual Activa", (x1 + 30, y1 + 50),
                cv2.FONT_HERSHEY_DUPLEX, 0.9, (0, 255, 150), 2)
    cv2.putText(frame, f"Resolucion: {width}x{height} @ {TARGET_FPS} FPS", (x1 + 30, y1 + 95),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 220, 220), 2)
    cv2.putText(frame, f"FPS Actual: {current_fps:.1f} | Frame #{frame_idx}", (x1 + 30, y1 + 135),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 255), 2)
    cv2.putText(frame, f"Hora local: {timestamp_str} (Driver: UnityCapture)", (x1 + 30, y1 + 175),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)
    
    # Barra de progreso cíclica
    bar_w = int((box_w - 60) * ((frame_idx % 90) / 90.0))
    cv2.rectangle(frame, (x1 + 30, y1 + 195), (x1 + 30 + bar_w, y1 + 203), (0, 220, 255), -1)

    return frame

def run_test(duration_seconds: int = 30):
    print("=" * 60)
    print("      AppCam - Test de Camara Virtual (Fase 0)")
    print("=" * 60)
    print(f"Resolucion objetivo: {WIDTH}x{HEIGHT} @ {TARGET_FPS} FPS")
    print(f"Backend: unitycapture (Driver DirectShow independiente)")
    print("Iniciando emision...")
    
    try:
        with pyvirtualcam.Camera(
            width=WIDTH,
            height=HEIGHT,
            fps=TARGET_FPS,
            fmt=pyvirtualcam.PixelFormat.BGR,
            backend='unitycapture'
        ) as cam:
            print(f"\n[OK] Camara virtual conectada exitosamente!")
            print(f"Dispositivo del sistema: '{cam.device}'")
            print(f"Puedes abrir la app 'Camara' de Windows o Meet/Zoom para ver la senal.")
            print(f"Transmitiendo durante {duration_seconds} segundos (o presiona Ctrl+C para salir)...\n")
            
            frame_count = 0
            start_time = time.time()
            fps_timer = start_time
            current_fps = float(TARGET_FPS)
            
            while True:
                now = time.time()
                elapsed = now - start_time
                if duration_seconds > 0 and elapsed >= duration_seconds:
                    print(f"\n[OK] Tiempo de prueba ({duration_seconds}s) completado con exito.")
                    break
                    
                # Calcular FPS instantáneo cada segundo
                if now - fps_timer >= 1.0:
                    current_fps = frame_count / (now - start_time)
                    fps_timer = now
                    sys.stdout.write(f"\rEmitiendo: {elapsed:.1f}s | FPS: {current_fps:.1f} | Frame: {frame_count}")
                    sys.stdout.flush()
                
                # Generar y enviar fotograma
                frame = create_test_pattern(frame_count, WIDTH, HEIGHT, current_fps)
                cam.send(frame)
                frame_count += 1
                
                # Mantener el ritmo de fotogramas
                cam.sleep_until_next_frame()
                
    except RuntimeError as e:
        print(f"\n[AVISO] {e}")
        print("\nPara resolverlo:")
        print("1. Ejecuta 'driver\\install_driver.bat' (haz doble clic o ejecutalo como Administrador).")
        print("2. Vuelve a ejecutar este script de prueba.")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Ocurrio un error inesperado: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nPrueba detenida por el usuario.")

if __name__ == "__main__":
    seconds = 30
    if len(sys.argv) > 1:
        try:
            seconds = int(sys.argv[1])
        except ValueError:
            pass
    run_test(seconds)
