from setuptools import setup, find_packages

setup(
    name="monitor",
    version="0.1.0",
    packages=["monitor"],
    package_dir={"monitor": "src/monitor"},
    install_requires=[
        "opencv-python",
        "requests",
        "numpy"
    ],
    entry_points={
        "console_scripts": [
            "monitor=monitor.main:main",
        ],
    },
    python_requires=">=3.7",
)