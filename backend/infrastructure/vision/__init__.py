"""
[Infrastructure Layer] Vision System Package
"""
try:
    from .camera import Camera
    from .pipeline import VisionPipeline
    from .preprocess import Preprocessor
    from .detection.opencv_dnn_detector import Detector
    from .roi_optimizer import ROIOptimizer
except Exception:
    import logging
    logging.getLogger(__name__).debug("Modular vision imports failed", exc_info=True)
