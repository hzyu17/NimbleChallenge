import time
import numpy as np

from PIL import Image, ImageDraw


def generate_frames(frame_queue, fps=150):
    width, height = 400, 300
    radius = 20
    x, y = 100, 100
    dx, dy = 5, 4
    delay = 1 / fps

    while True:
        # Create white background
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="blue")

        # Convert to NumPy array and send to queue
        frame = np.array(img).tolist()
        
        if len(frame_queue) >= 1:           
            frame_queue[0] = {
                "frame": frame,
                "center": (x, y)
            }
                        
        else:
            frame_queue.append(
                {
                "frame": frame,
                "center": (x, y)
                }
            )  # init
                
        # if not queue.full():
        #     queue.put(frame)

        # Update position
        x += dx
        y += dy
        if x - radius < 0 or x + radius > width:
            dx *= -1
        if y - radius < 0 or y + radius > height:
            dy *= -1

        time.sleep(delay)
