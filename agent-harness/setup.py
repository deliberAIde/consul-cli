from setuptools import find_namespace_packages, setup


setup(
    name="cli-anything-consul",
    version="0.2.0",
    description="Full operator CLI for CONSUL DEMOCRACY and compatible forks",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    include_package_data=True,
    install_requires=["click>=8.1", "click-repl>=0.3", "httpx>=0.27"],
    extras_require={"dev": ["pytest>=8", "ruff>=0.4"]},
    entry_points={
        "console_scripts": [
            "cli-anything-consul=cli_anything.consul.consul_cli:main",
            "consul=cli_anything.consul.consul_cli:main",
        ]
    },
    python_requires=">=3.11",
)
