import os
import pathlib
import random
from typing import Dict, Optional, Tuple

import typer
import vpype as vp
from cookiecutter.main import cookiecutter
from multiprocess.pool import Pool

import vsketch

from .gui import show
from .utils import (
    canonical_name,
    get_config_path,
    load_config,
    load_sketch_class,
    print_error,
    print_info,
)

cli = typer.Typer()


def _find_candidates(path: pathlib.Path, glob: str) -> Optional[pathlib.Path]:
    candidates = list(path.glob(glob))
    if len(candidates) == 1:
        return candidates[0].absolute()
    elif len(candidates) > 1:
        raise ValueError(
            f"target {path.absolute()} is ambiguous, possible scripts:\n"
            + "\n".join(f" - {candidate.name}" for candidate in candidates)
        )
    else:
        return None


def _find_sketch_script(path: Optional[str]) -> pathlib.Path:
    """Implements the logics of finding the sketch script:

    - if path is dir, look for a unique ``sketch_*.py`` file (return if exists, fail if many)
    - if none, look for a unique  ``*.py`` file (return if exists, fail if none or many)
    - if path is file, check if it ends with ``.py`` and fail otherwise

    """
    path = pathlib.Path().cwd() if path is None else pathlib.Path(path)

    if path.is_dir():
        # find  suitable sketch
        candidate_path = _find_candidates(path, "sketch_*.py")
        if candidate_path is None:
            candidate_path = _find_candidates(path, "*.py")

        if candidate_path is None:
            raise ValueError(
                f"target directory {path.absolute()} does not contain a sketch script"
            )
        else:
            return candidate_path
    elif path.suffix == ".py":
        return path.absolute()
    else:
        raise ValueError(f"target {path.absolute()} is not a Python file")


INIT_HELP = f"""Create a new sketch project.

This command creates a new directory named TARGET and containing the structure for a new
sketch project. TARGET may also be a path to the directory to be created.

If not provided, the page size and orientation is requested with an
interactive prompt. The page size may be one of:

    {', '.join(vp.PAGE_SIZES.keys())}

Alternatively, a custom size can be specified in the form of WIDTHxHEIGHT. WIDTH and
HEIGHT may include units. If only one has an unit, the other is assumed to have the
same unit. If none have units, both are assumed to be pixels by default. Here are some
examples:

\b
    --page-size 11x14in     # 11in by 14in
    --page-size 1024x768    # 1024px by 768px
    --page-size 13.5inx4cm  # 13.5in by 4cm

Portrait orientation is enforced, unless --landscape is used, in which case landscape
orientation is enforced.

By default, the new project is based on the official template located here:

    https://github.com/abey79/cookiecutter-vsketch-sketch

You can provide an alternative template address with the --template option.
 
Most options can use environment variables to set their default values. For example, the
default template can be set with the VSK_TEMPLATE variable and the default page size with the
VSK_PAGE_SIZE variable.
"""


@cli.command(help=INIT_HELP)
def init(
    target: str = typer.Argument(..., help="project name or path"),
    page_size: str = typer.Option(
        "a4",
        "--page-size",
        "-p",
        prompt=True,
        metavar="PAGESIZE",
        envvar="VSK_PAGE_SIZE",
        help="page size",
    ),
    landscape: bool = typer.Option(
        False,
        "--landscape",
        "-l",
        prompt=True,
        envvar="VSK_LANDSCAPE",
        help="use landscape orientation",
    ),
    template: str = typer.Option(
        "https://github.com/abey79/cookiecutter-vsketch-sketch.git",
        envvar="VSK_TEMPLATE",
        metavar="TEMPLATE",
        show_default=False,
        help="project template",
    ),
) -> None:
    """Init command."""

    dir_path = pathlib.Path(target)

    with vsketch.working_directory(dir_path.parent):
        cookiecutter(
            template,
            no_input=True,
            extra_context={
                "sketch_name": dir_path.name,
                "page_size": page_size,
                "landscape": str(landscape),
            },
        )


def _parse_seed(seed: str) -> Tuple[int, int]:
    seed_parts = seed.split("..")
    if len(seed_parts) == 1:
        return int(seed_parts[0]), int(seed_parts[0])
    elif len(seed_parts) == 2:
        return int(seed_parts[0]), int(seed_parts[1])
    else:
        raise ValueError(f"error parsing seed {seed}")


@cli.command()
def run(
    target: Optional[str] = typer.Argument(default=None, help="sketch directory or file"),
    editor: Optional[str] = typer.Option(
        None,
        "-e",
        "--editor",
        metavar="EDITOR",
        envvar="VSK_EDITOR",
        help="open the sketch file in EDITOR",
    ),
    fullscreen: bool = typer.Option(
        False,
        envvar="VSK_FULLSCREEN",
        help="display the viewer fullscreen on the second screen if available",
    ),
) -> None:
    """Execute, display and monitor changes on a sketch.

    This command loads a sketch and opens an interactive viewer display the result. The viewer
    will refresh the display each time the sketch file is saved. If the sketch defines any
    parameters, they will be displayed by the viewer and may be interactively changed.

    TARGET may either point at a Python file or at a directory. If omitted, the current
    directory is assumed. When TARGET points at a directory, this command looks for a single
    Python file whose name starts wit `sketch_`. If none are found, it will look for a single
    Python file with arbitrary name. If no or multiple candidates are found, the command will
    fail.

    If the --editor option is provided or the VSK_EDITOR environment variable is set, the
    sketch file will be opened with the corresponding editor.

    If the --fullscreen option is provided or the VSK_FULLSCREEN environment variable is set,
    and a second screen is available, the viewer is opened in fullscreen on the second monitor.
    """
    try:
        path = _find_sketch_script(target)
    except ValueError as err:
        print_error("Sketch could not be found: ", str(err))
        raise typer.Exit(code=1)

    print_info("Running sketch: ", str(path))

    if editor is not None and editor != "":
        os.system(f"{editor} {path}")

    show(str(path), second_screen=fullscreen)


@cli.command()
def save(
    target: Optional[str] = typer.Argument(default=None, help="sketch directory or file"),
    name: Optional[str] = typer.Option(
        None, "-n", "--name", help="output name (without extension)"
    ),
    config: Optional[str] = typer.Option(
        None,
        "-c",
        "--config",
        help=(
            "path to the config file to use (may be a path to JSON file or the name of the "
            "configuration)"
        ),
    ),
    seed: Optional[str] = typer.Option(None, "-s", "--seed", help="seed or seed range to use"),
    destination: Optional[str] = typer.Option(
        None, "-d", "--destination", help="destination path"
    ),
    multiprocessing: bool = typer.Option(
        True, envvar="VSK_MULTIPROCESSING", help="enable multiprocessing"
    ),
) -> None:
    """Save the sketch to a SVG file.

    By default, the output is named after the sketch and the provided options. An alternative
    name my be provided with the --name option.

    If the sketch as parameters, their default values are used. Alternatively, a pre-existing
    configuration can be used instead with the --config option.

    By default, a random seed is used for vsketch's random number generator. If --config is
    used, the seed saved in the configuration is used instead. A seed may also be provided with
    the --seed option, in which case it will override the configuration's seed.

    The --seed option also accepts seed range in the form of FIRST..LAST, e.g. 0..100. In this
    case, one output file per seed is generated.

    If the number of files to generate is greater than 4, all available cores are used for the
    process. This behaviour can be disabled with --no-multiprocessing or the
    VSK_MULTIPROCESSING variable.

    By default, all SVG are saved in the sketch's "output" sub-directory. This can be
    overridden using the --destination option.
    """

    try:
        path = _find_sketch_script(target)
    except ValueError as err:
        print_error("Sketch could not be found: ", str(err))
        raise typer.Exit(code=1)

    # load configuration
    param_set: Dict[str, vsketch.ParamType] = {}
    config_postfix = ""
    if config is not None:
        config_path = pathlib.Path(config)
        if not config_path.exists():
            config_path = get_config_path(path) / (config + ".json")

        if config_path.exists():
            param_set = load_config(config_path)
            config_postfix = "_" + config_path.stem
        else:
            print_error("Config file not found: ", str(config_path))

    # compute name
    if name is None:
        name = canonical_name(path) + config_postfix
    seed_in_name = seed is not None

    if seed is None:
        if param_set is not None and "__seed__" in param_set:
            seed_start = seed_end = int(param_set["__seed__"])
        else:
            seed_start = seed_end = random.randint(0, 2 ** 31 - 1)
    else:
        try:
            seed_start, seed_end = _parse_seed(seed)
        except ValueError as err:
            print_error(f"Could not parse seed {seed}: ", str(err))
            raise typer.Exit(code=1)

    # prepare output path
    if destination is not None:
        output_path = pathlib.Path(destination)
        if not output_path.exists():
            print_error("Provided output path does not exist: ", str(output_path.absolute()))
            raise typer.Exit(code=1)
        if not output_path.is_dir():
            print_error(
                "Provided output path is not a directory: ", str(output_path.absolute())
            )
            raise typer.Exit(code=1)
    else:
        output_path = path.parent / "output"
        if not output_path.exists():
            output_path.mkdir()
        elif not output_path.is_dir():
            print_error("Could not create output directory: ", str(output_path))
            raise typer.Exit(code=1)

    # noinspection PyShadowingNames
    def _write_output(seed: int) -> None:
        # this needs to be there because the sketch class cannot be pickled apparently
        sketch_class = load_sketch_class(path)
        if sketch_class is None:
            print_error("Could not load script: ", str(path))
            raise typer.Exit(code=1)

        sketch_class.set_param_set(param_set)

        output_name = name
        if seed_in_name:
            output_name += "_s" + str(seed)  # type: ignore
        output_name += ".svg"  # type: ignore

        output_file = output_path / output_name

        sketch = sketch_class.execute(finalize=True, seed=seed)

        if sketch is None:
            print_error("Could not execute script: ", str(path))
            raise typer.Exit(code=1)

        doc = sketch.vsk.document
        with open(output_file, "w") as fp:
            print_info("Exporting SVG: ", str(output_file))
            vp.write_svg(
                fp, doc, source_string=f"vsketch save -s {seed} {path}", color_mode="layer"
            )

    seed_range = range(seed_start, seed_end + 1)

    if len(seed_range) < 4 or not multiprocessing:
        for s in seed_range:
            _write_output(s)
    else:
        with Pool() as p:
            list(p.imap(_write_output, seed_range))


if __name__ == "__main__":
    save(target="examples/simple_sketch", name=None, seed="0", multiprocessing=True)
