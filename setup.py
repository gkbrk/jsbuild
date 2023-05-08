from distutils.core import setup

setup(
    name="js-build-cli",
    py_modules=["jsbuild"],
    entry_points={"console_scripts": ["jsbuild=jsbuild:main"]},
    version="0.0.5",
    description="Low bandwidth DoS tool. Slowloris rewrite in Python.",
    author="Gokberk Yaltirakli",
    author_email="opensource@gkbrk.com",
    url="https://github.com/gkbrk/jsbuild",
    keywords=["javascript", "build", "package", "minify", "uglify"],
    license="Apache License 2.0",
)
