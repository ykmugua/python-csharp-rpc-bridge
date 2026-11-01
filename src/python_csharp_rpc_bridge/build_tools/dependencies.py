from __future__ import annotations

import ast
import shutil
from pathlib import Path


def _resolve_module(root: Path, module: str) -> list[Path]:
    parts = module.split(".")
    files = []
    for index, part in enumerate(parts):
        relative = Path(*parts[: index + 1])
        module_file = root / relative.with_suffix(".py")
        package_file = root / relative / "__init__.py"
        if module_file.is_file():
            if index != len(parts) - 1:
                return []
            files.append(module_file)
            return files
        if package_file.is_file():
            files.append(package_file)
            continue
        return []
    return files


def _module_name(path: Path, root: Path) -> tuple[str, ...]:
    relative = path.relative_to(root).with_suffix("")
    return relative.parts[:-1]


def _imports(path: Path, root: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = _module_name(path, root)
                keep = len(package) - node.level + 1
                if keep < 0:
                    continue
                base = package[:keep]
                if node.module:
                    base += tuple(node.module.split("."))
                if base:
                    imports.append(".".join(base))
                    imports.extend(f"{'.'.join(base)}.{alias.name}" for alias in node.names)
            elif node.module:
                imports.append(node.module)
                imports.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return imports


def copy_local_dependencies(source: Path, output_dir: Path) -> list[Path]:
    """Copy recursively imported local Python modules beside the generated backend."""
    root = source.parent.resolve()
    source = source.resolve()
    reserved = {
        output_dir / source.name,
        output_dir / f"{source.stem}_rpc_server.py",
    }
    pending = [source]
    visited: set[Path] = set()
    dependencies: set[Path] = set()

    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        for module in _imports(current, root):
            for dependency in _resolve_module(root, module):
                if dependency not in visited:
                    pending.append(dependency)
                    if dependency != source:
                        dependencies.add(dependency)

    copied = []
    for dependency in sorted(dependencies):
        relative = dependency.relative_to(root)
        destination = output_dir / relative
        if destination in reserved:
            raise FileExistsError(f"Local dependency conflicts with generated backend file: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dependency, destination)
        copied.append(destination)
    return copied
