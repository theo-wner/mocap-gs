from setuptools import setup, find_packages

setup(
    name='mocap_ids_stream',
    version='0.1.0',
    packages=find_packages(include=['streams', 'streams.*']),
    install_requires=[
        'numpy',
        'opencv-python',
        'matplotlib',
        'scipy',
        'ids_peak',
    ],
)
