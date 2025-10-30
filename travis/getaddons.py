#!/usr/bin/env python
"""
Usage: get-addons [-m] path1 [path2 ...]
Given a list  of paths, finds and returns a list of valid addons paths.
With -m flag, will return a list of modules names instead.
"""

import ast
import logging
import os
import sys

from git_run import GitRun

logger = logging.getLogger(__name__)

MANIFEST_FILES = [
    "__manifest__.py",
    "__odoo__.py",
    "__openerp__.py",
    "__terp__.py",
]


def resolve_path(path):
    """Resolve symlinks and return the real path"""
    if os.path.islink(path):
        real_path = os.path.realpath(path)
        logger.info(f"Symlink detected: {path} -> {real_path}")
        return real_path
    return path


def is_module(path):
    """return False if the path doesn't contain an odoo module, and the full
    path to the module manifest otherwise"""
    # Resolve symlink if present
    resolved_path = resolve_path(path)

    if not os.path.isdir(resolved_path):
        return False

    files = os.listdir(resolved_path)
    filtered = [x for x in files if x in (MANIFEST_FILES + ["__init__.py"])]
    if len(filtered) == 2 and "__init__.py" in filtered:
        return os.path.join(
            resolved_path, next(x for x in filtered if x != "__init__.py")
        )
    else:
        return False


def is_installable_module(path):
    """return False if the path doesn't contain an installable odoo module,
    and the full path to the module manifest otherwise"""
    manifest_path = is_module(path)
    logger.info(manifest_path)
    if manifest_path:
        manifest = ast.literal_eval(open(manifest_path).read())
        if manifest.get("installable", True):
            return manifest_path
    return False


def get_modules(path):
    # Avoid empty basename when path ends with slash
    if not os.path.basename(path):
        path = os.path.dirname(path)

    # Resolve symlink if the main path is a symlink
    resolved_path = resolve_path(path)

    res = []
    if os.path.isdir(resolved_path):
        # Get all items in directory
        items = os.listdir(resolved_path)
        for item in items:
            item_path = os.path.join(resolved_path, item)

            # Check if item is installable module
            if is_installable_module(item_path):
                # If it's a symlink, get the real path for the module
                if os.path.islink(item_path):
                    real_item_path = os.path.realpath(item_path)
                    # Get the basename of the real path for the module name
                    res.append(os.path.basename(real_item_path))
                    logger.info(f"Added symlinked module: {item} -> {real_item_path}")
                else:
                    res.append(item)

    return res


def is_addons(path):
    res = get_modules(path) != []
    return res


def get_addons(path):
    if not os.path.exists(path):
        return []

    # Resolve main path if it's a symlink
    resolved_path = resolve_path(path)

    if is_addons(resolved_path):
        res = [resolved_path]
        # Buscar addons válidos dentro de este addon también (búsqueda recursiva)
        if os.path.isdir(resolved_path):
            items = sorted(os.listdir(resolved_path))
            for item in items:
                # Saltar directorios ocultos
                if item.startswith('.'):
                    continue
                    
                item_path = os.path.join(resolved_path, item)
                
                # Buscar recursivamente addons dentro
                if os.path.isdir(item_path):
                    nested_addons = get_addons(item_path)
                    res.extend(nested_addons)
    else:
        res = []
        if os.path.isdir(resolved_path):
            items = sorted(os.listdir(resolved_path))
            for item in items:
                item_path = os.path.join(resolved_path, item)

                # Check if item is an addon directory
                if is_addons(item_path):
                    # If it's a symlink, add the real path
                    if os.path.islink(item_path):
                        real_item_path = os.path.realpath(item_path)
                        res.append(real_item_path)
                        logger.info(
                            f"Added symlinked addon path: {item_path} -> {real_item_path}"
                        )
                    else:
                        res.append(item_path)
                    # Búsqueda recursiva de addons anidados
                    nested_addons = get_addons(item_path)
                    # Remover el item_path mismo de los resultados anidados (ya fue agregado)
                    nested_addons = [x for x in nested_addons if x != item_path]
                    res.extend(nested_addons)

    # Remove duplicates while preserving order
    seen = set()
    unique_res = []
    for item in res:
        if item not in seen:
            seen.add(item)
            unique_res.append(item)

    return unique_res


def get_modules_changed(path, ref="HEAD"):
    """Get modules changed from git diff-index {ref}
    :param path: String path of git repo
    :param ref: branch or remote/branch or sha to compare
    :return: List of paths of modules changed
    """
    # Resolve symlink if the main path is a symlink
    resolved_path = resolve_path(path)

    git_run_obj = GitRun(os.path.join(resolved_path, ".git"))
    if ref != "HEAD":
        fetch_ref = ref
        if ":" not in fetch_ref:
            # to force create branch
            fetch_ref += ":" + fetch_ref
        git_run_obj.run(["fetch"] + fetch_ref.split("/", 1))

    items_changed = git_run_obj.get_items_changed(ref)
    folders_changed = set(
        [
            item_changed.split("/")[0]
            for item_changed in items_changed
            if "/" in item_changed
        ]
    )

    modules = set(get_modules(resolved_path))
    modules_changed = list(modules & folders_changed)
    modules_changed_path = [
        os.path.join(resolved_path, module_changed)
        for module_changed in modules_changed
    ]

    return modules_changed_path


def main(argv=None):
    if argv is None:
        argv = sys.argv

    params = argv[1:]
    if not params:
        print(__doc__)
        return 1

    list_modules = False
    exclude_modules = []

    while params and params[0].startswith("-"):
        param = params.pop(0)
        if param == "-m":
            list_modules = True
        if param == "-e":
            exclude_modules = [x for x in params.pop(0).split(",")]

    func = get_modules if list_modules else get_addons
    lists = [func(x) for x in params]
    res = [x for l in lists for x in l]  # flatten list of lists

    if exclude_modules:
        res = [x for x in res if x not in exclude_modules]

    result = ",".join(res)
    print(result)
    return result


if __name__ == "__main__":
    main()
