"""Lazy OCR recognition and explicit raw/name text boundaries."""

from pathlib import Path
from names import canonical


def _read_raw(reader, images):
    method = getattr(reader, 'read_raw', None)
    return method(images) if method is not None else reader.read(images)


def _read_names(reader, images):
    method = getattr(reader, 'read_names', None)
    return method(images) if method is not None else reader.read(images)


class TextReader:
    """Load only the small recognition model, with one CPU inference thread."""

    def __init__(self, lazy=False):
        self.reader = None
        if not lazy:
            self._load()

    def _load(self):
        import onnxruntime as ort
        import rapidocr_onnxruntime
        from rapidocr_onnxruntime.ch_ppocr_v3_rec.text_recognize import TextRecognizer
        from rapidocr_onnxruntime.ch_ppocr_v3_rec.utils import CTCLabelDecode

        model = Path(rapidocr_onnxruntime.__file__).parent / 'models/ch_PP-OCRv3_rec_infer.onnx'
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        session = ort.InferenceSession(str(model), sess_options=options,
                                       providers=['CPUExecutionProvider'])
        input_name = session.get_inputs()[0].name
        reader = TextRecognizer.__new__(TextRecognizer)
        reader.session = lambda batch: session.run(None, {input_name: batch})
        reader.postprocess_op = CTCLabelDecode(
            session.get_modelmeta().custom_metadata_map['character'].splitlines())
        reader.rec_batch_num = 3
        reader.rec_image_shape = [3, 48, 320]
        self.reader = reader

    def read_raw(self, images):
        if self.reader is None:
            self._load()
        rows, _ = self.reader(images)
        return [(str(text).strip(), float(score)) for text, score in rows]

    def read_names(self, images):
        return [(canonical(text), score) for text, score in self.read_raw(images)]

    def read(self, images):
        return self.read_names(images)
