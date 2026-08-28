from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import torch
from PIL import Image

PROMPT = "</s><s><predict_bbox><predict_classes><output_markdown><predict_no_text_in_pic>"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_path", type=Path)
    parser.add_argument("page_manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    model_path = args.model_path.resolve()
    if not (model_path / "model.safetensors").exists():
        raise FileNotFoundError(f"Nemotron model is incomplete: {model_path}")
    sys.path.insert(0, str(model_path))
    runtime_cache = model_path.parent
    os.environ["HF_HOME"] = str(runtime_cache / "huggingface")
    os.environ["HF_MODULES_CACHE"] = str(runtime_cache / "transformers_modules")
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    from transformers import AutoModel, AutoProcessor, GenerationConfig
    from postprocessing import extract_classes_bboxes, postprocess_text, transform_bbox_to_original

    device = "cuda:0"
    model = AutoModel.from_pretrained(str(model_path), trust_remote_code=True, local_files_only=True, torch_dtype=torch.bfloat16).to(device).eval()
    processor = AutoProcessor.from_pretrained(str(model_path), trust_remote_code=True, local_files_only=True)
    generation = GenerationConfig.from_pretrained(str(model_path), local_files_only=True)
    page_manifest = json.loads(args.page_manifest.read_text(encoding="utf-8"))
    parsed_pages = []
    with torch.inference_mode():
        for page_info in page_manifest["pages"]:
            image = Image.open(page_info["path"]).convert("RGB")
            inputs = processor(images=[image], text=PROMPT, return_tensors="pt", add_special_tokens=False).to(device)
            output_ids = model.generate(**inputs, generation_config=generation)
            generated = processor.batch_decode(output_ids, skip_special_tokens=True)[0]
            classes, bboxes, texts = extract_classes_bboxes(generated)
            if not (len(classes) == len(bboxes) == len(texts)):
                raise ValueError(f"Nemotron output arrays differ on page {page_info['page']}")
            elements = []
            for order, (semantic_class, bbox, text) in enumerate(zip(classes, bboxes, texts)):
                transformed = transform_bbox_to_original(bbox, image.width, image.height)
                cleaned = postprocess_text(text, cls=semantic_class, table_format="markdown", text_format="markdown", blank_text_in_figures=False)
                if cleaned.strip():
                    elements.append({"order": order, "semantic_class": semantic_class, "bbox": list(transformed), "text": cleaned})
            parsed_pages.append({"page": page_info["page"], "width": image.width, "height": image.height, "elements": elements, "generated_text": generated})
    if not parsed_pages or not any(page["elements"] for page in parsed_pages):
        raise ValueError("PARSE_EMPTY: Nemotron returned no document elements")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"parser": "nvidia/NVIDIA-Nemotron-Parse-v1.2", "model_path": str(model_path), "prompt": PROMPT, "page_count": len(parsed_pages), "pages": parsed_pages}, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
