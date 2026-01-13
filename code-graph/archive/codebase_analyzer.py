from __future__ import annotations

import ast
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


class CodebaseAnalyzer:
    def __init__(self):
        self.root_dir = Path(__file__).parent.parent.parent
        self.analysis = {
            "metadata": {"generated": datetime.now().isoformat(), "root_dir": str(self.root_dir)},
            "files": {},
            "dependencies": {},
            "js_dependencies": {},
            "statistics": {},
        }

    def scan_files(self):
        """Find all relevant code files - COMPREHENSIVE VERSION (excluding tests)."""
        python_files = []
        js_files = []

        python_patterns = [
            "shopq/**/*.py",
            "scripts/**/*.py",
            "experiments/**/*.py",
            "api/**/*.py",
        ]

        for pattern in python_patterns:
            for file in self.root_dir.glob(pattern):
                file_str = str(file)
                if (
                    "__pycache__" not in file_str
                    and "venv" not in file_str
                    and "test" not in file.name.lower()
                    and "/tests/" not in file_str
                    and "/test_" not in file_str
                ):
                    python_files.append(file)

        js_patterns = ["extension/**/*.js"]

        for pattern in js_patterns:
            for file in self.root_dir.glob(pattern):
                file_str = str(file)
                if "node_modules" not in file_str and "test" not in file.name.lower():
                    js_files.append(file)

        return python_files, js_files

    def analyze_python_file(self, filepath):
        """Analyze a Python file using AST."""
        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
                tree = ast.parse(content)

            info = {
                "type": "python",
                "path": str(filepath.relative_to(self.root_dir)),
                "lines": len(content.split("\n")),
                "docstring": ast.get_docstring(tree) or "",
                "imports": [],
                "internal_imports": [],  # ✅ Will now map to FILE paths
                "external_imports": [],
                "classes": [],
                "functions": [],
                "complexity": 0,
            }

            # Extract imports
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        info["imports"].append(alias.name)
                        if alias.name.startswith(("mailq", "scripts", "api", "experiments")):
                            # ✅ Convert module to file path
                            file_path = self._module_to_file_path(alias.name)
                            if file_path:
                                info["internal_imports"].append(file_path)
                        else:
                            info["external_imports"].append(alias.name)

                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        full_import = f"{module}.{alias.name}" if module else alias.name
                        info["imports"].append(full_import)

                        if module.startswith(("mailq", "scripts", "api", "experiments")):
                            # ✅ Convert module to file path
                            file_path = self._module_to_file_path(module)
                            if file_path:
                                info["internal_imports"].append(file_path)
                        else:
                            info["external_imports"].append(full_import)

                elif isinstance(node, ast.ClassDef):
                    methods = [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                    info["classes"].append(
                        {
                            "name": node.name,
                            "methods": methods,
                            "method_count": len(methods),
                            "docstring": ast.get_docstring(node) or "",
                        }
                    )
                    info["complexity"] += len(methods)

                elif isinstance(node, ast.FunctionDef) and node.col_offset == 0:
                    info["functions"].append(
                        {"name": node.name, "docstring": ast.get_docstring(node) or ""}
                    )
                    info["complexity"] += 1

            # Remove duplicates
            info["internal_imports"] = list(set(info["internal_imports"]))

            return info

        except Exception as e:
            return {
                "type": "python",
                "path": str(filepath.relative_to(self.root_dir)),
                "error": str(e),
            }

    def _module_to_file_path(self, module_name):
        """Convert Python module name to file path.

        Examples:
            shopq.memory_classifier → shopq/memory_classifier.py
            shopq.config → shopq/config/__init__.py
            scripts.check_schema → scripts/check_schema.py
        """
        # Remove any trailing imports (e.g., shopq.config.Config → shopq.config)
        parts = module_name.split(".")

        # Try as a direct file first
        direct_path = "/".join(parts) + ".py"
        if (self.root_dir / direct_path).exists():
            return direct_path

        # Try as a package (__init__.py)
        package_path = "/".join(parts) + "/__init__.py"
        if (self.root_dir / package_path).exists():
            return package_path

        # Try parent as package (for imports like shopq.config.Config)
        if len(parts) > 1:
            parent_path = "/".join(parts[:-1]) + ".py"
            if (self.root_dir / parent_path).exists():
                return parent_path

            parent_package = "/".join(parts[:-1]) + "/__init__.py"
            if (self.root_dir / parent_package).exists():
                return parent_package

        return None

    def analyze_js_file(self, filepath):
        """Analyze a JavaScript file - NOW WITH IMPORTS."""
        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()

            description = ""
            for line in content.split("\n")[:20]:
                if "/**" in line or "*" in line:
                    cleaned = line.strip().lstrip("/*").lstrip("*").strip()
                    if cleaned and not cleaned.startswith("*/"):
                        description = cleaned
                        break

            imports = []
            internal_imports = []

            for line in content.split("\n"):
                if "import" in line and "from" in line:
                    if "'" in line:
                        parts = line.split("'")
                        if len(parts) >= 2:
                            path = parts[1]
                    elif '"' in line:
                        parts = line.split('"')
                        if len(parts) >= 2:
                            path = parts[1]
                    else:
                        continue

                    imports.append(path)

                    if path.startswith("./") or path.startswith("../"):
                        # ✅ Resolve relative path to absolute
                        current_dir = filepath.parent.relative_to(self.root_dir)
                        if path.startswith("./"):
                            resolved = current_dir / path[2:]
                        else:  # ../
                            resolved = current_dir / path

                        # Normalize and add .js if missing
                        resolved = str(resolved).replace(".js", "") + ".js"
                        resolved = str(Path(resolved).as_posix())
                        internal_imports.append(resolved)

            return {
                "type": "javascript",
                "path": str(filepath.relative_to(self.root_dir)),
                "lines": len(content.split("\n")),
                "description": description,
                "imports": imports,
                "internal_imports": internal_imports,
                "has_async": "async" in content,
                "has_fetch": "fetch(" in content,
                "has_export": "export" in content,
                "has_import": "import" in content,
            }

        except Exception as e:
            return {
                "type": "javascript",
                "path": str(filepath.relative_to(self.root_dir)),
                "error": str(e),
            }

    def build_dependency_graph(self):
        """Build dependency relationships for Python - FILE TO FILE."""
        deps = defaultdict(list)

        for path, info in self.analysis["files"].items():
            if info.get("type") == "python" and "internal_imports" in info:
                for target_file in info["internal_imports"]:
                    if target_file and target_file != path:
                        deps[path].append(target_file)

        return dict(deps)

    def build_js_dependency_graph(self):
        """Build dependency relationships for JavaScript."""
        deps = defaultdict(list)

        for path, info in self.analysis["files"].items():
            if info.get("type") == "javascript" and "internal_imports" in info:
                for target_file in info["internal_imports"]:
                    if target_file and target_file != path:
                        deps[path].append(target_file)

        return dict(deps)

    def calculate_statistics(self):
        """Calculate statistics."""
        files = self.analysis["files"]

        stats = {
            "total_files": len(files),
            "python_files": len([f for f in files.values() if f.get("type") == "python"]),
            "js_files": len([f for f in files.values() if f.get("type") == "javascript"]),
            "total_lines": sum(f.get("lines", 0) for f in files.values()),
            "total_classes": sum(len(f.get("classes", [])) for f in files.values()),
            "total_functions": sum(len(f.get("functions", [])) for f in files.values()),
            "orchestrators": [],
            "core_classes": [],
            "by_directory": {},
        }

        for path, info in files.items():
            dir_name = path.split("/")[0]
            if dir_name not in stats["by_directory"]:
                stats["by_directory"][dir_name] = {
                    "files": 0,
                    "lines": 0,
                    "python": 0,
                    "javascript": 0,
                }
            stats["by_directory"][dir_name]["files"] += 1
            stats["by_directory"][dir_name]["lines"] += info.get("lines", 0)
            if info.get("type") == "python":
                stats["by_directory"][dir_name]["python"] += 1
            elif info.get("type") == "javascript":
                stats["by_directory"][dir_name]["javascript"] += 1

        for path, info in files.items():
            internal_import_count = len(info.get("internal_imports", []))
            if internal_import_count >= 3:
                stats["orchestrators"].append(
                    {
                        "path": path,
                        "import_count": internal_import_count,
                        "docstring": info.get("docstring", ""),
                        "type": info.get("type", "unknown"),
                    }
                )

        for path, info in files.items():
            for cls in info.get("classes", []):
                if cls["method_count"] >= 5:
                    stats["core_classes"].append(
                        {
                            "path": path,
                            "class_name": cls["name"],
                            "method_count": cls["method_count"],
                            "docstring": cls.get("docstring", ""),
                        }
                    )

        stats["orchestrators"].sort(key=lambda x: x["import_count"], reverse=True)
        stats["core_classes"].sort(key=lambda x: x["method_count"], reverse=True)

        return stats

    def analyze(self):
        """Run full analysis."""
        python_files, js_files = self.scan_files()

        for py_file in python_files:
            rel_path = str(py_file.relative_to(self.root_dir))
            self.analysis["files"][rel_path] = self.analyze_python_file(py_file)

        for js_file in js_files:
            rel_path = str(js_file.relative_to(self.root_dir))
            self.analysis["files"][rel_path] = self.analyze_js_file(js_file)

        self.analysis["dependencies"] = self.build_dependency_graph()
        self.analysis["js_dependencies"] = self.build_js_dependency_graph()
        self.analysis["statistics"] = self.calculate_statistics()

        return self.analysis


if __name__ == "__main__":
    analyzer = CodebaseAnalyzer()
    result = analyzer.analyze()
    print(json.dumps(result, indent=2))
