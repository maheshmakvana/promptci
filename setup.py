from setuptools import setup, find_packages

setup(
    name="promptci",
    version="1.1.0",
    description="Prompt versioning with CI/CD regression gates — version, test, diff, and deploy prompts with quality gates, schema evolution, PII scrubbing, and full observability",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/maheshmakvana/promptci",
    packages=find_packages(exclude=["tests*", "venv*"]),
    python_requires=">=3.8",
    install_requires=[
        "pydantic>=2.0",
    ],
    extras_require={
        "dev": ["pytest>=7.0", "pytest-asyncio>=0.21"],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords=[
        "prompt versioning", "prompt management", "llm ci cd",
        "prompt testing", "regression gates", "prompt engineering",
        "prompt registry", "ai ci cd", "prompt diff",
        "schema evolution", "prompt quality", "llm deployment",
        "prompt validation", "ai engineering", "llm ops",
        "prompt pipeline", "ai testing", "prompt observability",
        "pii scrubbing", "llm quality gates",
    ],
)
