"""Independent offline PDFium text/rendering for manual recovery evidence."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pack", type=Path, required=True)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--render-hash")
    p.add_argument("--page", type=int)
    args = p.parse_args()
    import pypdfium2 as pdfium
    data = args.archive.read_bytes()
    output = args.pack / "manual" / hashlib.sha256(data).hexdigest() / "pdfium"
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            if member.is_dir() or member.file_size > 100_000_000:
                continue
            raw = archive.read(member)
            if not raw.startswith(b"%PDF-"):
                continue
            digest = hashlib.sha256(raw).hexdigest()
            if args.render_hash and args.render_hash != digest:
                continue
            target = output / (digest + ".json")
            if not args.render_hash and not target.exists():
                previous = sorted((args.pack / "manual").glob("*/pdfium/" + target.name))
                if previous:
                    target.write_bytes(previous[0].read_bytes())
            with pdfium.PdfDocument(raw) as doc:
                if args.render_hash:
                    page = doc[args.page - 1]
                    page.render(scale=1.5).to_pil().save(output / f"{digest}-{args.page}.png")
                    page.close()
                    continue
                if target.exists():
                    continue
                pages = []
                for i in range(len(doc)):
                    page = doc[i]
                    text = page.get_textpage()
                    pages.append(text.get_text_range())
                    text.close()
                    page.close()
            body = json.dumps({"source_sha256": digest, "pages": pages}, sort_keys=True).encode()
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(body)
            temporary.replace(target)
            print(json.dumps({"file": member.filename, "pages": len(pages), "sha256": digest}), flush=True)


if __name__ == "__main__":
    main()
