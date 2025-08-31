#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Downloader YouTube com pytubefix
- Saída padrão: pasta Downloads do usuário (fallback: ./downloads)
- Suporta: vídeo único, áudio-only, vídeo-only, playlist, qualidade alvo, merge com FFmpeg
- Python 3.13+

Uso rápido:
  python downloader.py --url "https://youtu.be/..." --qualidade 1080p
  python downloader.py --url "https://youtu.be/..." --audio-only
  python downloader.py --url "https://www.youtube.com/playlist?list=PL..." --playlist --max-itens 5
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List

from pytubefix import YouTube, Playlist

# ======================== Config / Constantes ========================

QUALIDADES = ("best", "2160p", "1440p", "1080p", "720p", "480p", "360p")
INVALID_CHARS = r'<>:"/\\|?*\0'
INVALID_RE = re.compile(rf"[{re.escape(INVALID_CHARS)}]")

# ======================== Utilidades ========================

def default_download_dir() -> Path:
    """
    Tenta resolver a pasta Downloads do usuário (Windows/Unix).
    Fallback: ./downloads
    """
    candidates: List[Path] = []
    # Windows
    userprofile = os.getenv("USERPROFILE")
    if userprofile:
        candidates.append(Path(userprofile) / "Downloads")
    # Unix-like
    candidates.append(Path.home() / "Downloads")
    # Fallback local
    candidates.append(Path.cwd() / "downloads")

    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            # Teste rápido de escrita
            p = d / ".probe_write"
            p.write_text("ok", encoding="utf-8")
            p.unlink(missing_ok=True)
            return d
        except Exception:
            continue
    return Path.cwd()

def sanitize_filename(name: str, max_len: int = 120) -> str:
    name = INVALID_RE.sub("_", (name or "video")).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    return name[:max_len] if len(name) > max_len else name

def human_time(seconds: int) -> str:
    seconds = int(seconds or 0)
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

def dedupe_path(base: Path) -> Path:
    if not base.exists():
        return base
    stem, suffix = base.stem, base.suffix
    n = 1
    while True:
        cand = base.with_name(f"{stem} ({n}){suffix}")
        if not cand.exists():
            return cand
        n += 1

# ======================== Progresso ========================

@dataclass
class ProgressState:
    filesize: int = 0
    started_at: float = 0.0
    last_report: float = 0.0

def make_progress_cb(state: ProgressState):
    def _cb(stream, chunk, bytes_remaining):
        if state.filesize == 0:
            try:
                state.filesize = int(getattr(stream, "filesize", 0) or 0)
            except Exception:
                state.filesize = 0
        now = time.time()
        if state.started_at == 0:
            state.started_at = now
        if state.last_report and (now - state.last_report) < 0.25:
            return
        done = (state.filesize - int(bytes_remaining or 0)) if state.filesize else 0
        pct = (done / state.filesize * 100) if state.filesize else 0
        elapsed = now - state.started_at
        speed = (done / (1024 * 1024)) / elapsed if elapsed > 0 else 0  # MB/s
        eta = (state.filesize - done) / (speed * 1024 * 1024) if speed > 0 else math.inf
        eta_txt = human_time(int(eta)) if math.isfinite(eta) else "--:--"
        sys.stdout.write(f"\r[download] {pct:6.2f}% | {speed:6.2f} MB/s | ETA {eta_txt}")
        sys.stdout.flush()
        state.last_report = now
    return _cb

def end_progress_line():
    sys.stdout.write("\n")
    sys.stdout.flush()

# ======================== Seleção de streams ========================

def pick_quality(target: str) -> str:
    t = (target or "").lower().strip()
    if t in QUALIDADES:
        return t
    m = re.fullmatch(r"(\d{3,4})p?", t)
    if m:
        t = f"{m.group(1)}p"
        return t if t in QUALIDADES else "best"
    return "best"

def select_streams(yt: YouTube, qualidade: str, audio_only: bool, video_only: bool) -> Tuple[Optional[object], Optional[object], bool]:
    """
    Retorna (video_stream, audio_stream, need_merge).
    Regras:
      - audio_only: melhor áudio disponível
      - video_only: vídeo sem áudio (adaptive)
      - caso comum: tenta progressive na qualidade pedida; se não houver, cai em adaptive (v+a) com merge
    """
    q = pick_quality(qualidade)

    if audio_only:
        a = yt.streams.filter(only_audio=True).order_by("abr").desc().first()
        return None, a, False

    if video_only:
        if q == "best":
            v = yt.streams.filter(only_video=True).order_by("resolution").desc().first()
        else:
            v = yt.streams.filter(only_video=True, res=q).first() or \
                yt.streams.filter(only_video=True).order_by("resolution").desc().first()
        return v, None, False

    # Tenta progressive
    prog = yt.streams.filter(progressive=True)
    if q != "best":
        cand = prog.filter(res=q).order_by("resolution").desc().first()
        if cand:
            return cand, None, False
    best_prog = prog.order_by("resolution").desc().first()

    # Tenta adaptive (mais comum para 1080p+)
    v = (yt.streams.filter(only_video=True, res=q).first()
         if q != "best" else yt.streams.filter(only_video=True).order_by("resolution").desc().first())
    if not v:
        v = yt.streams.filter(only_video=True).order_by("resolution").desc().first()
    a = yt.streams.filter(only_audio=True).order_by("abr").desc().first()
    if v and a:
        return v, a, True

    # Fallback progressive best
    if best_prog:
        return best_prog, None, False

    raise RuntimeError("Nenhum stream adequado encontrado.")

# ======================== FFmpeg / Merge ========================

def has_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg"))

def merge_av(video_path: Path, audio_path: Path, out_path: Path, aac_bitrate: str = "192k") -> Path:
    """
    Gera MP4 final:
      - Vídeo: copy
      - Áudio: se .webm/opus → reencode AAC; senão copy
      - -movflags +faststart
    """
    out_path = out_path.with_suffix(".mp4")
    audio_is_webm = audio_path.suffix.lower() == ".webm"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy",
    ]
    if audio_is_webm:
        cmd += ["-c:a", "aac", "-b:a", aac_bitrate]
    else:
        cmd += ["-c:a", "copy"]
    cmd += ["-movflags", "+faststart", str(out_path)]

    logging.debug("FFmpeg: %s", " ".join(cmd))
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou: {res.stderr.decode(errors='ignore')[:500]}")
    return out_path

# ======================== Download ========================

def download_single(
    url: str,
    outdir: Path,
    qualidade: str = "best",
    audio_only: bool = False,
    video_only: bool = False,
    sem_merge: bool = False,
    aac_bitrate: str = "192k",
) -> Optional[Path]:
    for attempt in range(1, 4):
        try:
            prog_state = ProgressState()
            yt = YouTube(url, on_progress_callback=make_progress_cb(prog_state))
            title = sanitize_filename(yt.title or "video")
            author = getattr(yt, "author", "?")
            length = human_time(getattr(yt, "length", 0))
            logging.info('Vídeo: "%s" | Autor: %s | Duração: %s', title, author, length)

            v, a, need_merge = select_streams(yt, qualidade, audio_only, video_only)

            # Áudio-only
            if audio_only and a:
                base = dedupe_path(outdir / f"{title}.m4a")
                logging.info("Baixando áudio → %s", base.name)
                path = a.download(output_path=outdir, filename=base.name)
                end_progress_line()
                return Path(path)

            # Sem merge (progressive ou fluxo único)
            if not need_merge or sem_merge:
                stream = v or a
                subtype = getattr(stream, "subtype", None) or "mp4"
                info = getattr(stream, "resolution", None) or getattr(stream, "abr", None) or "stream"
                base = dedupe_path(outdir / f"{title}.{subtype}")
                logging.info("Baixando (%s) → %s", info, base.name)
                path = stream.download(output_path=outdir, filename=base.name)
                end_progress_line()
                return Path(path)

            # Adaptive + merge
            if need_merge:
                if not has_ffmpeg():
                    logging.warning("ffmpeg não encontrado. Fallback para melhor progressive, se existir.")
                    prog = yt.streams.filter(progressive=True).order_by("resolution").desc().first()
                    if prog:
                        base = dedupe_path(outdir / f"{title}.{prog.subtype or 'mp4'}")
                        logging.info("Baixando (progressive fallback) → %s", base.name)
                        path = prog.download(output_path=outdir, filename=base.name)
                        end_progress_line()
                        return Path(path)
                    raise RuntimeError("Sem ffmpeg e sem progressive disponível.")

                v_ext = v.subtype or "mp4"
                a_ext = a.subtype or "m4a"
                v_path = dedupe_path(outdir / f"{title}.video.{v_ext}")
                a_path = dedupe_path(outdir / f"{title}.audio.{a_ext}")

                logging.info("Baixando VÍDEO → %s", v_path.name)
                v.download(output_path=outdir, filename=v_path.name)
                end_progress_line()

                logging.info("Baixando ÁUDIO → %s", a_path.name)
                a.download(output_path=outdir, filename=a_path.name)
                end_progress_line()

                final = dedupe_path(outdir / f"{title}.mp4")
                logging.info("Unindo (ffmpeg) → %s", final.name)
                merged = merge_av(v_path, a_path, final, aac_bitrate=aac_bitrate)

                # Limpando temporários
                try:
                    v_path.unlink(missing_ok=True)
                    a_path.unlink(missing_ok=True)
                except Exception:
                    pass

                return merged

            raise RuntimeError("Fluxo inesperado de seleção de streams.")

        except Exception as e:
            end_progress_line()
            logging.warning("Tentativa %d falhou: %s", attempt, e)
            if attempt == 3:
                logging.error("Falhou após 3 tentativas.")
                return None
            wait = 1.5 ** attempt
            logging.info("Aguardando %.1fs para tentar novamente…", wait)
            time.sleep(wait)

def is_playlist_url(url: str) -> bool:
    return "list=" in (url or "")

def download_playlist(
    url: str,
    outdir: Path,
    qualidade: str = "best",
    audio_only: bool = False,
    video_only: bool = False,
    sem_merge: bool = False,
    max_itens: Optional[int] = None,
    aac_bitrate: str = "192k",
) -> None:
    pl = Playlist(url)
    urls: List[str] = list(pl.video_urls)
    if max_itens:
        urls = urls[:max_itens]
    logging.info("Playlist: %d itens", len(urls))
    for i, vurl in enumerate(urls, 1):
        logging.info("--- [%d/%d] %s", i, len(urls), vurl)
        _ = download_single(
            url=vurl,
            outdir=outdir,
            qualidade=qualidade,
            audio_only=audio_only,
            video_only=video_only,
            sem_merge=sem_merge,
            aac_bitrate=aac_bitrate,
        )

# ======================== CLI ========================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Downloader YouTube (pytubefix) com merge MP4 + AAC.")
    p.add_argument("--url", required=True, help="URL de vídeo ou playlist do YouTube")
    p.add_argument("--saida", default=None, help="Diretório de saída (default: Downloads do sistema ou ./downloads)")
    p.add_argument("--qualidade", default="best", choices=list(QUALIDADES), help="Qualidade desejada")
    p.add_argument("--audio-only", action="store_true", help="Baixar apenas áudio (m4a)")
    p.add_argument("--video-only", action="store_true", help="Baixar apenas vídeo (sem áudio)")
    p.add_argument("--sem-merge", action="store_true", help="Não unir adaptativo com ffmpeg; baixa apenas um stream")
    p.add_argument("--playlist", action="store_true", help="Forçar modo playlist mesmo com URL de vídeo")
    p.add_argument("--max-itens", type=int, default=None, help="Limite de itens da playlist")
    p.add_argument("--log-level", default="INFO", help="DEBUG/INFO/WARN/ERROR (default: INFO)")
    p.add_argument("--aac-bitrate", default="192k", help="Bitrate do AAC no merge (ex.: 128k, 160k, 192k)")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s: %(message)s",
    )

    outdir = Path(args.saida).expanduser().resolve() if args.saida else default_download_dir()
    outdir.mkdir(parents=True, exist_ok=True)
    logging.info("Saída: %s", outdir)
    logging.info("Qualidade desejada: %s", args.qualidade)

    if args.playlist or is_playlist_url(args.url):
        download_playlist(
            url=args.url,
            outdir=outdir,
            qualidade=args.qualidade,
            audio_only=args.audio_only,
            video_only=args.video_only,
            sem_merge=args.sem_merge,
            max_itens=args.max_itens,
            aac_bitrate=args.aac_bitrate,
        )
    else:
        path = download_single(
            url=args.url,
            outdir=outdir,
            qualidade=args.qualidade,
            audio_only=args.audio_only,
            video_only=args.video_only,
            sem_merge=args.sem_merge,
            aac_bitrate=args.aac_bitrate,
        )
        if path:
            logging.info("Concluído → %s", path.name)
        else:
            logging.error("Não foi possível concluir o download.")

if __name__ == "__main__":
    main()
