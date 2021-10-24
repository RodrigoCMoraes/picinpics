import os
import cv2


input_directory = "images"
output_directory = "resize"
factor = 0.2


filenames = [
    (os.path.join(root, name), name)
    for root, _, files in os.walk(input_directory)
    for name in files
]
for filename, name in filenames:
    img = cv2.imread(filename)
    if img is None:
        continue
    img = cv2.resize(img, (0, 0), fx=factor, fy=factor)
    output_filename = os.path.join(output_directory, name)
    cv2.imwrite(output_filename, img)
