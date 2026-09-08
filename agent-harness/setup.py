from pathlib import Path

from setuptools import find_namespace_packages, setup


setup(
    name="consul-democracy-cli",
    version="0.2.0",
    description="Full operator CLI for CONSUL DEMOCRACY and compatible municipal forks",
    long_description=(Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="deliberAIde",
    author_email="info@deliberaide.com",
    license="Apache-2.0",
    url="https://github.com/deliberAIde/consul-cli",
    project_urls={
        "Repository": "https://github.com/deliberAIde/consul-cli",
        "Agent-bridges toolkit": "https://github.com/deliberAIde/civic-tech-agent-bridges",
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.11",
        "Topic :: Utilities",
    ],
    packages=find_namespace_packages(include=["cli_anything.*"]),
    include_package_data=True,
    install_requires=["click>=8.1", "click-repl>=0.3", "httpx>=0.27"],
    extras_require={"dev": ["pytest>=8", "ruff>=0.4"]},
    entry_points={
        "console_scripts": [
            "consul-democracy=cli_anything.consul.consul_cli:main",
            "cli-anything-consul=cli_anything.consul.consul_cli:main",
            # `consul` shadows HashiCorp Consul's binary if both are installed; see README.
            "consul=cli_anything.consul.consul_cli:main",
        ]
    },
    python_requires=">=3.11",
)
