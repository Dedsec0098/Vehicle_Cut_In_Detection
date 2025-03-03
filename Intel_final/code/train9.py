import cv2
import numpy as np
from ultralytics import YOLO
from shapely.geometry import Polygon, Point
import tkinter as tk
from tkinter import filedialog
import os
import glob
import math
import matplotlib.pyplot as plt

global apparent_width
global speed
global actual_pixel

model = YOLO("yolov8s.pt")

speed = 4  # m/s
focal_length = 500  # Example value, replace with actual focal length
real_car_width = 1.4  # Width of a car in meters
actual_pixel = 310

# Define the vehicle classes
vehicle_classes = ["car", "truck", "bus", "motorbike", "bicycle"]

# Function to detect vehicles in an image
def detect_vehicles(image_path):
    img = cv2.imread(image_path)
    img = cv2.resize(img, (640, 640))
    height, width, _ = img.shape

    # Run YOLOv8 model
    results = model(img, device='cpu')

    # Initialize lists for detected bounding boxes, confidences, class IDs, and distances
    boxes = []
    confidences = []
    class_ids = []
    distances = []

    # Extract information from the detections
    for result in results:
        for bbox in result.boxes:
            x, y, w, h = map(int, bbox.xywh[0])  # Convert to integers
            confidence = float(bbox.conf[0])  # Convert to float
            class_id = int(bbox.cls[0])  # Convert to integer

            if confidence > 0.65:
                boxes.append([x, y, w, h])
                confidences.append(confidence)
                class_ids.append(class_id)

                # Calculate distance
                distance = (real_car_width * focal_length) / w
                distances.append(distance)

    # Apply non-max suppression to eliminate redundant overlapping boxes with lower confidences
    indexes = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)

    detected_vehicles = []
    for i in indexes:
        x, y, w, h = boxes[i]
        detected_vehicles.append((x, y, w, h, distances[i]))
    
    return detected_vehicles, img, width, height

# Intersection over Union (IoU) function
def iou(box1, box2):
    x1, y1, w1, h1, _ = box1
    x2, y2, w2, h2, _ = box2
    xi1, yi1 = max(x1, x2), max(y1, y2)
    xi2, yi2 = min(x1 + w1, x2 + w2), min(y1 + h1, y2 + h2)
    inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    box1_area = w1 * h1
    box2_area = w2 * h2
    union_area = box1_area + box2_area - inter_area
    return inter_area / union_area if union_area != 0 else 0

# Detect potential cut-ins and calculate speed and TTC
def detect_potential_cut_ins_and_ttc(frame1_vehicles, frame2_vehicles, width, height, time_interval, iou_threshold=0.45):
    potential_cut_ins = []
    ttc_vehicles = []

    for box2 in frame2_vehicles:
        best_match = None
        best_iou = 0
        for box1 in frame1_vehicles:
            current_iou = iou(box1, box2)
            if current_iou > best_iou:
                best_iou = current_iou
                best_match = box1

        if best_iou < iou_threshold:
            # This is a new vehicle or a vehicle that has moved significantly
            x2, y2, w2, h2, dist2 = box2
            distance_from_center = np.sqrt((x2 + w2/2 - width/2)*2 + (y2 + h2/2 - height)*2)
            theta = 2 * math.atan((real_car_width / 2) / distance_from_center)
            apparent_width = 2 * distance_from_center * math.tan(theta / 2)

            pixels = round((apparent_width * actual_pixel) / real_car_width)
            upper_left_x = 320 - round(pixels / 2)
            upper_right_x = 320 + round(pixels / 2)
            det_left_x = x2 
            det_left_y = y2 + h2
            det_right_x = x2 + w2
            det_right_y = y2 + h2
            region = Polygon([(130, 640), (440, 640), (upper_left_x, 340), (upper_right_x, 340)])

            if region.contains(Point(det_left_x, det_left_y)) or region.contains(Point(det_right_x, det_right_y)):
                ttc = distance_from_center / speed
                if speed > 0:
                    potential_cut_ins.append(box2)
                    if ttc < 2 and best_iou < iou_threshold:
                        ttc_vehicles.append((box2, ttc))

    return potential_cut_ins, ttc_vehicles

def select_folder():
    # Create a Tkinter root window
    root = tk.Tk()
    root.withdraw()  # Hide the root window

    # Open the folder selection dialog
    folder_path = filedialog.askdirectory()

    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
    
    # Initialize an empty list to store image file paths
    image_file_paths = []

    # Loop through each image extension and find all matching files
    for extension in image_extensions:
        image_file_paths.extend(glob.glob(os.path.join(folder_path, f'*{extension}')))

    return image_file_paths

# Get the list of image file paths
frame_paths = select_folder()

time_interval = 0  # Example value, adjust as needed

# Process all frames
for i in range(len(frame_paths) - 1):
    frame1_path = frame_paths[i]
    frame2_path = frame_paths[i + 1]

    # Detect vehicles in both frames
    frame1_vehicles, frame1_img, width, height = detect_vehicles(frame1_path)
    frame2_vehicles, frame2_img, _, _ = detect_vehicles(frame2_path)

    # Detect potential cut-ins and calculate TTC between the two frames
    potential_cut_ins, ttc_vehicles = detect_potential_cut_ins_and_ttc(frame1_vehicles, frame2_vehicles, width, height, time_interval)
    
    # Draw bounding boxes and calculate distances
    for (x, y, w, h, distance) in frame2_vehicles:
        time = distance / speed  # Time calculation
        bottom_left_x = x
        bottom_left_y = y + h
        color = (0, 255, 0)  # Green color for bounding box by default

        corners = [
            Point(x, y),
            Point(x + w, y),
            Point(x, y + h),
            Point(x + w, y + h)
        ]
        
        distance_from_center = np.sqrt((x + w/2 - width/2)*2 + (y + h/2 - height)*2)
        theta = 2 * math.atan((real_car_width / 2) / distance_from_center)
        apparent_width = 2 * distance_from_center * math.tan(theta / 2)
        pixels = round((apparent_width * actual_pixel) / real_car_width)
        upper_left_x = 320 - round(pixels / 2)
        upper_right_x = 320 + round(pixels / 2)
            
        checkpoint = Point(bottom_left_x, bottom_left_y)
        region = Polygon([(200, 640), (620, 640), (upper_left_x, 340), (upper_right_x, 340)])

        # Polygon region for checking
        
        # Check if any corner is within the polygon region and if time < 3 seconds
        if any(region.contains(corner) for corner in corners) and time < 1.7:
            color = (0, 0, 255)  # Red color if within the polygon region and time < 3 seconds
        
        # Draw bounding box
        cv2.rectangle(frame2_img, (int(x), int(y)), (int(x + w), int(y + h)), color, 2)
        cv2.putText(frame2_img, f'Dist: {distance:.2f}m Time: {time:.2f}s', (int(bottom_left_x), int(bottom_left_y + 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)  # Distance and Time
    
    # Draw TTC for cut-in vehicles
    for ((x, y, w, h, distance), ttc) in ttc_vehicles:
        bottom_left_x = x
        bottom_left_y = y + h
        color = (0, 0, 255)  # Red color if within the polygon region
        cv2.rectangle(frame2_img, (int(x), int(y)), (int(x + w), int(y + h)), color, 2)
        cv2.putText(frame2_img, f'Dist: {distance:.2f}m TTC: {ttc:.2f}s', (int(bottom_left_x), int(bottom_left_y + 40)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    # Display the output image with bounding boxes, distances, and TTC
    cv2.imshow(f'Frame {i+2}', frame2_img)
    cv2.waitKey(1000)  # Waitkey
    cv2.destroyWindow(f'Frame {i+2}')  # Close
