"""Comando `ngband`. Subcomandos de compilación: gfx y adpcm."""
import argparse
import sys
from pathlib import Path


def _cmd_gfx(args: argparse.Namespace) -> int:
    # Los gráficos se generan en compilación (R1.9): ROM C, tiles fijos, persp[] y paletas.
    from .gfx import run
    r = run(Path(args.out), rebuild_font=args.rebuild_font)
    print(f"gfx: {len(r.c1) // 64} tiles de sprite, {len(r.srom) // 32} tiles fijos, {len(r.persp)} filas de perspectiva")
    return 0
def _cmd_adpcm(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "adpcm_data.c").write_text("/* generado por `ngband adpcm` */\n", encoding="utf-8")
    return 0


def _cmd_list_songs(args: argparse.Namespace) -> int:
    from .songlist import write_song_list
    names = write_song_list(Path(args.out), release=args.release)
    print("\n".join(names))
    return 0


def _cmd_export_notes(args: argparse.Namespace) -> int:
    """Las notas de un VGM en el formato de bandcore.notes, para arreglarlas en otra consola: los canales de
    guitarra, teclado y bajo (los que elegiría import-song, o los que se pidan) y la batería con sus papeles."""
    from bandcore import notes as bnotes

    from . import drums as dr
    from .songgen import OPTION_KEYS, drum_assignment, load_song
    opts = {"name": "export", "source": str(Path(args.source).resolve())}
    for key in OPTION_KEYS:
        if getattr(args, key, None):
            opts[key] = getattr(args, key)
    try:
        sd = load_song(opts)
    except ValueError as exc:
        print(f"ngband: {exc}", file=sys.stderr)
        return 1
    channels = {
        slot: [[n.frame, n.duration, n.pitch, bnotes.DEFAULT_VOLUME] for n in sd.channel_notes(sd.assign.get(inst, []))]
        for slot, inst in (("Square1", "guitarra"), ("Square2", "teclado"), ("Triangle", "bajo"))
    }
    assignment = drum_assignment(sd)
    hits = [[h.frame, h.role, h.cymbal] for h in dr.drum_hits(sd.notes, sd.drums, assignment)] if assignment else []
    data = bnotes.make(sd.title, sd.game, sd.stream_frames, channels, hits)
    bnotes.write(data, Path(args.out))
    used = ", ".join(f"{inst} {'+'.join(sd.assign.get(inst, []))}" for inst in ("guitarra", "teclado", "bajo"))
    print(f"{args.out}: {sd.title} ({sd.game}), {sd.stream_frames / 60:.1f} s; {used}; "
          f"batería {'+'.join(sd.drums)} ({len(hits)} golpes)")
    return 0


def _cmd_channels(args: argparse.Namespace) -> int:
    from .songgen import describe_channels
    try:
        print("\n".join(describe_channels(Path(args.source), args.duration)))
    except ValueError as exc:
        print(f"ngband: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_import_song(args: argparse.Namespace) -> int:
    from .songgen import OPTION_KEYS, ROOT, import_song
    source = Path(args.source).resolve()
    try:
        rel = source.relative_to(ROOT)
    except ValueError:
        rel = source
    opts: dict = {"name": args.name, "source": rel.as_posix()}
    for key in OPTION_KEYS:
        value = getattr(args, key)
        if value is not None:
            opts[key] = value
    try:
        print("\n".join(import_song(opts)))
    except ValueError as exc:  # ImportError_ y los errores del lector de VGM: no se escribió nada
        print(f"ngband: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_edit_chart(args: argparse.Namespace) -> int:
    from .editor import serve
    try:
        serve(args.name, args.port, not args.no_browser)
    except (ValueError, OSError) as exc:  # canción sin import.json, VGM inválido, puerto ocupado
        print(f"ngband: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_reimport(args: argparse.Namespace) -> int:
    from .songgen import reimport_song
    try:
        print("\n".join(reimport_song(args.name)))
    except ValueError as exc:  # sin import.json, VGM inválido, ediciones injugables: no se escribió nada
        print(f"ngband: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ngband")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("channels", help="muestra las notas y la altura de cada canal de un VGM")
    p.add_argument("source", help=".vgm o .vgz")
    p.add_argument("--duration", type=float, help="segundos (repite el bucle)")
    p.set_defaults(fn=_cmd_channels)
    p = sub.add_parser("export-notes", help="saca las notas de un VGM a JSON (bandcore.notes) para arreglarlas en otra consola")
    p.add_argument("source", help=".vgm o .vgz")
    p.add_argument("--out", required=True)
    p.add_argument("--title")
    p.add_argument("--game")
    p.add_argument("--duration", type=float, help="segundos (repite el bucle)")
    for inst in ("guitarra", "teclado", "bajo", "bateria"):
        p.add_argument(f"--{inst}", help=f"canal(es) del {inst}: fm1..fm4, ssg1..ssg3, adpcma, adpcmb")
    p.set_defaults(fn=_cmd_export_notes)
    p = sub.add_parser("import-song", help="importa un VGM a src/songs/<nombre>/")
    p.add_argument("source", help=".vgm o .vgz")
    p.add_argument("--name", required=True, help="nombre de la carpeta (minúsculas, números y _)")
    p.add_argument("--title")
    p.add_argument("--game")
    p.add_argument("--duration", type=float, help="segundos; repite el bucle hasta llenarlos")
    p.add_argument("--beat-frames", dest="beat_frames", type=int, help="cuadros por tiempo")
    for inst in ("guitarra", "teclado", "bajo"):
        p.add_argument(f"--{inst}", help="canal(es): fm1..fm4, ssg1..ssg3, separados por coma")
    p.add_argument("--bateria", help="canal(es) de batería: adpcma, fm4, ssg3...")
    p.set_defaults(fn=_cmd_import_song)
    p = sub.add_parser("reimport", help="repite la importación con import.json, conservando drums.json y edits.json")
    p.add_argument("name", help="carpeta de src/songs/")
    p.set_defaults(fn=_cmd_reimport)
    p = sub.add_parser("edit-chart", help="abre el editor de charts en el navegador (127.0.0.1)")
    p.add_argument("name", nargs="?", help="carpeta de src/songs/ (sin ella, abre la pantalla de inicio)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true", help="no abrir el navegador")
    p.set_defaults(fn=_cmd_edit_chart)
    p = sub.add_parser("list-songs", help="lista las canciones de la ROM (orden alfabético)")
    p.add_argument("--out", default="build/gen")
    p.add_argument("--release", action="store_true", help="solo las canciones versionadas en git")
    p.set_defaults(fn=_cmd_list_songs)
    for name, fn, help_ in (("gfx", _cmd_gfx, "genera los gráficos"),
                            ("adpcm", _cmd_adpcm, "convierte los samples ADPCM-A")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--out", default="build/gen")
        if name == "gfx":
            p.add_argument("--rebuild-font", action="store_true",
                           help="regenera assets/fonts/bongo8_glyphs.txt desde la TTF (necesita Pillow)")
        p.set_defaults(fn=fn)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
