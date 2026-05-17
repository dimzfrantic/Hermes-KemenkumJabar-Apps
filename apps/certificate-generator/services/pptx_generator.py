from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from flask import current_app
from PIL import Image
from pptx import Presentation


def _normalize_replacements(replacements: dict[str, str]) -> dict[str, str]:
    normalized = {}
    for key, value in replacements.items():
        text = '' if value is None else str(value).strip()
        normalized[key] = text
    return normalized


def _replace_in_runs(paragraph, replacements: dict[str, str]) -> bool:
    if not paragraph.runs:
        return False

    changed = False
    for old, new in replacements.items():
        while True:
            runs = list(paragraph.runs)
            full_text = ''.join(run.text for run in runs)
            start = full_text.find(old)
            if start == -1:
                break

            end = start + len(old)
            run_ranges = []
            cursor = 0
            for idx, run in enumerate(runs):
                run_text = run.text or ''
                next_cursor = cursor + len(run_text)
                run_ranges.append((idx, cursor, next_cursor))
                cursor = next_cursor

            impacted = []
            for idx, run_start, run_end in run_ranges:
                overlap_start = max(start, run_start)
                overlap_end = min(end, run_end)
                if overlap_start < overlap_end:
                    impacted.append((idx, run_start, run_end, overlap_end - overlap_start))

            if not impacted:
                break

            anchor_idx = max(impacted, key=lambda item: item[3])[0]
            for idx, run_start, run_end, _ in impacted:
                run = runs[idx]
                original = run.text or ''
                local_token_start = max(start, run_start) - run_start
                local_token_end = min(end, run_end) - run_start
                prefix = original[:local_token_start]
                suffix = original[local_token_end:]
                run.text = f'{prefix}{new}{suffix}' if idx == anchor_idx else f'{prefix}{suffix}'
            changed = True
    return changed


def _replace_paragraph_text_preserve_style(paragraph, new_text: str):
    runs = list(paragraph.runs)
    if not runs:
        paragraph.text = new_text
        return

    anchor_run = runs[0]
    anchor_font = anchor_run.font
    font_name = anchor_font.name
    font_size = anchor_font.size
    font_bold = anchor_font.bold
    font_italic = anchor_font.italic
    font_underline = anchor_font.underline
    color_rgb = None
    try:
        if anchor_font.color.type is not None and anchor_font.color.rgb is not None:
            color_rgb = anchor_font.color.rgb
    except Exception:
        pass

    anchor_run.text = new_text
    for extra_run in runs[1:]:
        extra_run.text = ''

    anchor_font = anchor_run.font
    anchor_font.name = font_name
    anchor_font.size = font_size
    anchor_font.bold = font_bold
    anchor_font.italic = font_italic
    anchor_font.underline = font_underline
    try:
        if color_rgb is not None:
            anchor_font.color.rgb = color_rgb
    except Exception:
        pass



def _replace_in_shape(shape, replacements: dict[str, str]):
    for paragraph in shape.text_frame.paragraphs:
        changed = _replace_in_runs(paragraph, replacements)
        if not changed:
            raw_text = paragraph.text or ''
            updated = raw_text
            for old, new in replacements.items():
                updated = updated.replace(old, new)
            if updated != raw_text:
                _replace_paragraph_text_preserve_style(paragraph, updated)


def replace_placeholders(input_pptx: str, output_pptx: str, replacements: dict[str, str]):
    prs = Presentation(input_pptx)
    normalized = _normalize_replacements(replacements)
    for slide in prs.slides:
        for shape in slide.shapes:
            if not getattr(shape, 'has_text_frame', False):
                continue
            _replace_in_shape(shape, normalized)
    prs.save(output_pptx)


def _find_placeholder_shapes(prs: Presentation, placeholders: list[str]) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for slide_index, slide in enumerate(prs.slides):
        for shape_index, shape in enumerate(slide.shapes):
            if not getattr(shape, 'has_text_frame', False):
                continue
            text = shape.text or ''
            if any(token in text for token in placeholders):
                found.append((slide_index, shape_index))
    return found


def _validate_placeholder_shapes(prs: Presentation, placeholders: list[str]) -> list[tuple[int, int]]:
    if len(prs.slides) != 1:
        raise RuntimeError('Template sertifikat aman PDF hanya mendukung 1 slide. Gabungkan desain menjadi satu slide dengan background PNG dan textbox placeholder.')

    found = _find_placeholder_shapes(prs, placeholders)
    if not found:
        raise RuntimeError(
            'Placeholder template tidak ditemukan. Pastikan template PPTX memuat placeholder teks seperti {{nama}} dan {{instansi}}.'
        )

    for slide_index, shape_index in found:
        shape = prs.slides[slide_index].shapes[shape_index]
        if not getattr(shape, 'has_text_frame', False):
            raise RuntimeError('Placeholder harus berada pada textbox teks, bukan pada shape/grafik lain.')
        text = shape.text or ''
        cleaned = text
        for token in placeholders:
            cleaned = cleaned.replace(token, '')
        if cleaned.strip():
            raise RuntimeError(
                'Textbox placeholder hanya boleh berisi placeholder murni. '
                'Pindahkan ornamen/desain ke background PNG dan sisakan textbox untuk placeholder saja.'
            )
    return found


def _copy_textbox_style(src_shape, dest_shape):
    dest_shape.text_frame.clear()
    dest_shape.text_frame.word_wrap = src_shape.text_frame.word_wrap
    dest_shape.text_frame.auto_size = src_shape.text_frame.auto_size
    dest_shape.text_frame.margin_left = src_shape.text_frame.margin_left
    dest_shape.text_frame.margin_right = src_shape.text_frame.margin_right
    dest_shape.text_frame.margin_top = src_shape.text_frame.margin_top
    dest_shape.text_frame.margin_bottom = src_shape.text_frame.margin_bottom
    dest_shape.text_frame.vertical_anchor = src_shape.text_frame.vertical_anchor

    dest_shape.fill.background()
    dest_shape.line.fill.background()

    src_paragraphs = list(src_shape.text_frame.paragraphs)
    for paragraph_index, src_paragraph in enumerate(src_paragraphs):
        dest_paragraph = dest_shape.text_frame.paragraphs[0] if paragraph_index == 0 else dest_shape.text_frame.add_paragraph()
        dest_paragraph.alignment = src_paragraph.alignment
        dest_paragraph.level = src_paragraph.level
        try:
            dest_paragraph.line_spacing = src_paragraph.line_spacing
        except Exception:
            pass
        try:
            dest_paragraph.space_before = src_paragraph.space_before
        except Exception:
            pass
        try:
            dest_paragraph.space_after = src_paragraph.space_after
        except Exception:
            pass

        if not src_paragraph.runs:
            dest_paragraph.text = src_paragraph.text
            continue

        for src_run in src_paragraph.runs:
            dest_run = dest_paragraph.add_run()
            dest_run.text = src_run.text
            src_font = src_run.font
            dest_font = dest_run.font
            dest_font.name = src_font.name
            dest_font.size = src_font.size
            dest_font.bold = src_font.bold
            dest_font.italic = src_font.italic
            dest_font.underline = src_font.underline
            try:
                if src_font.color.type is not None and src_font.color.rgb is not None:
                    dest_font.color.rgb = src_font.color.rgb
            except Exception:
                pass


def resolve_soffice_path(configured: str = '') -> str:
    if configured:
        return configured
    for candidate in ('soffice', '/usr/bin/soffice', '/snap/bin/libreoffice'):
        if shutil.which(candidate) or Path(candidate).exists():
            return candidate
    raise RuntimeError('LibreOffice/soffice tidak ditemukan pada server.')


def _resolve_soffice() -> str:
    return resolve_soffice_path(current_app.config.get('SOFFICE_PATH', ''))


def _compress_png_for_pdf_target(
    png_path: str,
    max_bytes: int = 200 * 1024,
    min_width: int = 1800,
    min_height: int = 1200,
) -> str:
    path = Path(png_path)
    if not path.exists():
        return png_path

    with Image.open(path) as img:
        image = img.convert('RGB')
        width, height = image.size
        quality_steps = [92, 88, 84, 80, 76, 72]
        scale_steps = [1.0, 0.9, 0.82, 0.75, 0.68]
        best_candidate = None

        for scale in scale_steps:
            scaled_width = max(min_width, int(width * scale))
            scaled_height = max(min_height, int(height * scale))
            resized = image if (scaled_width, scaled_height) == (width, height) else image.resize((scaled_width, scaled_height), Image.LANCZOS)

            for quality in quality_steps:
                candidate = path.with_name(f'{path.stem}-optimized-{scaled_width}x{scaled_height}-q{quality}.jpg')
                resized.save(candidate, format='JPEG', quality=quality, optimize=True, progressive=True)
                size = candidate.stat().st_size
                best_candidate = candidate
                if size <= max_bytes:
                    try:
                        path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return str(candidate)

        if best_candidate is not None:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            return str(best_candidate)

    return png_path


def _convert_pptx_with_soffice(input_pptx: str, output_dir: str, target_format: str, soffice_path: str = '') -> str:
    soffice = resolve_soffice_path(soffice_path)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    profile_root = output_root / '_soffice_profiles'
    profile_root.mkdir(parents=True, exist_ok=True)
    profile_dir = profile_root / uuid4().hex
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_uri = profile_dir.resolve().as_uri()
    cmd = [
        soffice,
        '--headless',
        f'-env:UserInstallation={profile_uri}',
        '--convert-to',
        target_format,
        '--outdir',
        str(output_root),
        input_pptx,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    stdout = (result.stdout or '').strip()
    stderr = (result.stderr or '').strip()
    output_path = output_root / f'{Path(input_pptx).stem}.{target_format}'
    try:
        shutil.rmtree(profile_dir, ignore_errors=True)
    except Exception:
        pass
    if result.returncode != 0:
        details = stderr or stdout or 'tanpa output error dari LibreOffice'
        raise RuntimeError(
            f'Konversi {target_format.upper()} gagal. returncode={result.returncode}. '
            f'input={Path(input_pptx).name}. detail={details}'
        )
    if not output_path.exists():
        details = stderr or stdout or f'LibreOffice tidak menghasilkan file {target_format.upper()}'
        raise RuntimeError(
            f'File {target_format.upper()} hasil konversi tidak ditemukan. '
            f'input={Path(input_pptx).name}. detail={details}'
        )
    return str(output_path)


def build_pdf_safe_template(
    input_pptx: str,
    output_pptx: str,
    placeholders: list[str] | None = None,
    working_dir: str = '',
    soffice_path: str = '',
    cleanup_working_dir: bool = True,
) -> dict:
    source_path = Path(input_pptx)
    target_path = Path(output_pptx)
    placeholder_tokens = list(placeholders or ['{{nama}}', '{{instansi}}'])
    if not placeholder_tokens:
        raise RuntimeError('Daftar placeholder template kosong. Tidak dapat menyiapkan mode aman PDF.')

    work_root = Path(working_dir) if working_dir else (target_path.parent / f'_{target_path.stem}_pdf_safe_build')
    shutil.rmtree(work_root, ignore_errors=True)
    work_root.mkdir(parents=True, exist_ok=True)

    render_input = work_root / f'{source_path.stem}-blank-placeholders.pptx'
    replace_placeholders(
        str(source_path),
        str(render_input),
        {token: '' for token in placeholder_tokens},
    )
    rendered_png = Path(_convert_pptx_with_soffice(str(render_input), str(work_root), 'png', soffice_path))
    optimized_background = Path(_compress_png_for_pdf_target(str(rendered_png)))

    src_prs = Presentation(str(source_path))
    placeholder_refs = _validate_placeholder_shapes(src_prs, placeholder_tokens)

    output_prs = Presentation()
    output_prs.slide_width = src_prs.slide_width
    output_prs.slide_height = src_prs.slide_height
    output_slide = output_prs.slides.add_slide(output_prs.slide_layouts[6])
    output_slide.shapes.add_picture(
        str(optimized_background),
        0,
        0,
        width=output_prs.slide_width,
        height=output_prs.slide_height,
    )

    copied_shapes = []
    for slide_index, shape_index in placeholder_refs:
        src_shape = src_prs.slides[slide_index].shapes[shape_index]
        textbox = output_slide.shapes.add_textbox(src_shape.left, src_shape.top, src_shape.width, src_shape.height)
        _copy_textbox_style(src_shape, textbox)
        copied_shapes.append({
            'name': getattr(src_shape, 'name', f'shape-{shape_index}'),
            'text': src_shape.text,
            'slide_index': slide_index,
            'shape_index': shape_index,
        })

    if len(output_prs.slides) > 1:
        rel_id = output_prs.slides._sldIdLst[0].rId
        output_prs.part.drop_rel(rel_id)
        del output_prs.slides._sldIdLst[0]

    target_path.parent.mkdir(parents=True, exist_ok=True)
    output_prs.save(str(target_path))

    background_png_path = str(optimized_background)
    working_dir_path = str(work_root)
    if cleanup_working_dir:
        try:
            shutil.rmtree(work_root, ignore_errors=True)
        except Exception:
            pass

    return {
        'output_pptx': str(target_path),
        'background_png': background_png_path,
        'placeholder_count': len(copied_shapes),
        'placeholders': copied_shapes,
        'working_dir': working_dir_path,
        'working_dir_cleaned': cleanup_working_dir,
    }


def convert_document_with_soffice(input_path: str, output_dir: str, target_format: str, soffice_path: str = '') -> str:
    return _convert_pptx_with_soffice(input_path, output_dir, target_format, soffice_path)


def convert_pptx_to_pdf_with_soffice(input_pptx: str, output_dir: str, soffice_path: str = '') -> str:
    return convert_document_with_soffice(input_pptx, output_dir, 'pdf', soffice_path)


def convert_pptx_to_pdf(input_pptx: str, output_dir: str) -> str:
    return convert_pptx_to_pdf_with_soffice(input_pptx, output_dir, current_app.config.get('SOFFICE_PATH', ''))
