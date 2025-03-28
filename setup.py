from setuptools import setup

setup(
    name="hatch_colcon", 
    version="0.1.0",
    py_modules=["hatch"],
    install_requires=[
        'setuptools',
        'argparse',
        'PyYAML',
        'lxml',
        'colcon-common-extensions',
    ],
    entry_points={
        "console_scripts": [
            "hatch=hatch:main",
        ],
    },
    author="Marc Alban",
    author_email="marcalban@hatchbed.com",
    description="Command line tools for working with the colcon meta-buildsystem and colcon workspaces.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/hatchbed/hatch_colcon",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD 3-Clause License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)