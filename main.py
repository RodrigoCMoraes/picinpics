from typing import List, Tuple, NewType
import math
import os

import cv2
import numpy
from skimage.color import rgb2hsv
from tqdm import tqdm
from loguru import logger
from pathos.pools import ProcessPool
from sklearn.cluster import MiniBatchKMeans
from sklearn.utils import shuffle
from scipy.spatial import distance

Pixel = NewType("Pixel", Tuple[int, int, int])
Image = NewType("Image", numpy.dtype)


def files_in_directory(directory: str) -> List[Image]:
    filenames = [
        os.path.join(root, name)
        for root, _, files in os.walk(directory)
        for name in files
    ]
    pool = ProcessPool(nodes=os.cpu_count())
    results = pool.imap(lambda f: cv2.imread(f), filenames)
    return [r for r in tqdm(results, total=len(filenames)) if r is not None]


def normalize(
    images: List[Image], size: int, to_resize: bool = True, to_hsv: bool = False
) -> List[Image]:
    def _resize(image: Image, size: int, to_hsv: bool) -> Image:
        image = cv2.resize(image, (size, size))
        if to_hsv:
            image = rgb2hsv(image) * 255
        return image

    pool = ProcessPool(nodes=os.cpu_count())
    results = pool.imap(_resize, images, [size] * len(images), [to_hsv] * len(images))
    if not to_resize:
        results = images
    return list(tqdm(results, total=len(images)))


def quantize_image(image: Image) -> Pixel:
    pixels = numpy.float32(image.reshape(-1, 3))
    n_colours = 5

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 0.1)
    flags = cv2.KMEANS_RANDOM_CENTERS
    _, labels, centroid = cv2.kmeans(pixels, n_colours, None, criteria, 10, flags)
    labels = labels.flatten().tolist()
    _, counts = numpy.unique(labels, return_counts=True)
    dominant = centroid[numpy.argmax(counts)]
    return dominant


def quantize(images: List[Image]) -> List[Pixel]:
    pool = ProcessPool(nodes=os.cpu_count())
    results = pool.imap(quantize_image, images)
    return list(tqdm(results, total=len(images)))


def build_grid(
    input_img: Image, images: List[Image], pixel_list: List[Pixel], window_size
):
    def _find_closests_pixel(pixel: Pixel, pixel_list: List[Pixel]) -> int:
        results = map(lambda x: distance.euclidean(pixel, x), pixel_list)
        results = list(results)
        return numpy.argmin(results)

    height, width, _ = input_img.shape
    rois = list(
        input_img[y : y + window_size, x : x + window_size]
        for y in range(0, height, window_size)
        for x in range(0, width, window_size)
    )
    output_rows = int(math.ceil(height / window_size))
    output_cols = int(math.ceil(width / window_size))

    logger.info("quantizing to grid image")
    quantized_colors = quantize(rois)

    logger.info("finding closests images")
    pool = ProcessPool(nodes=os.cpu_count())
    results = pool.imap(
        _find_closests_pixel, quantized_colors, [pixel_list] * len(rois)
    )
    results = list(tqdm(results, total=len(rois)))

    logger.info("assemblying grid")
    grid_image = None
    for i in range(output_rows):
        for j in range(output_cols):
            pos = i * output_cols + j
            img = images[results[pos]]
            row = cv2.hconcat([row, img]) if j else img
        grid_image = cv2.vconcat([grid_image, row]) if i else row
    return grid_image


IMAGES_DIRECTORY = "pixel_images"
IMAGE_TO_GRID = "original.jpg"
SUB_IMAGE_SIZE = 16

logger.debug("to grid image read")
to_grid_img = cv2.imread(IMAGE_TO_GRID)
to_grid_img = rgb2hsv(to_grid_img) * 255

logger.info("reading files")
images = files_in_directory(IMAGES_DIRECTORY)
logger.info(f"{len(images)} retrieved files")

logger.info("images normalizing")
images_hsv = normalize(images, SUB_IMAGE_SIZE, to_hsv=True)
images_ = normalize(images, SUB_IMAGE_SIZE, to_hsv=False)

logger.info("quantizing color")
quantized_colors = quantize(images_hsv)

logger.info("building grid")
grid_image = build_grid(to_grid_img, images_, quantized_colors, SUB_IMAGE_SIZE)

cv2.imwrite("grid_image.png", grid_image)
logger.info("done")
