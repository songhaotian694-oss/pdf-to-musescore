"""Create a conservative grayscale raster PDF for a second Audiveris attempt."""
import argparse
import json
from pathlib import Path
import tempfile

import pypdfium2 as pdfium
from PIL import ImageOps
from pypdf import PdfReader, PdfWriter


def absolute(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f'Absolute path required: {value}')
    return path.resolve()


def convert(source, output, dpi):
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(str(source))
    writer = PdfWriter()
    pages = []
    try:
        with tempfile.TemporaryDirectory(prefix='omr-grayscale-', dir=str(output.parent)) as temporary:
            temporary = Path(temporary)
            for index in range(len(document)):
                page = document[index]
                try:
                    bitmap = page.render(scale=dpi / 72.0)
                    try:
                        gray = bitmap.to_pil().convert('L')
                        # Keep symbol geometry intact. Audiveris performs its own adaptive binarization.
                        image = ImageOps.autocontrast(gray, cutoff=0.25).convert('RGB')
                        page_pdf = temporary / f'page-{index + 1:04}.pdf'
                        image.save(page_pdf, 'PDF', resolution=dpi, quality=95)
                        writer.add_page(PdfReader(page_pdf).pages[0])
                        pages.append({'page': index + 1, 'widthPixels': image.width,
                                      'heightPixels': image.height})
                    finally:
                        bitmap.close()
                finally:
                    page.close()
            with output.open('xb') as stream:
                writer.write(stream)
    finally:
        document.close()
    return {'status': 'created', 'profile': f'grayscale-{dpi}', 'source': str(source),
            'output': str(output), 'dpi': dpi, 'pages': pages,
            'method': 'grayscale raster, light autocontrast, no sharpening or geometric edits'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--dpi', type=int, default=400, choices=range(200, 501))
    args = parser.parse_args()
    try:
        result = convert(absolute(args.input), absolute(args.output), args.dpi)
        report = absolute(args.report)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        code = 0
    except Exception as exc:
        result, code = {'status': 'failed', 'error': str(exc)}, 1
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
