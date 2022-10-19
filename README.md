# jsbuild - A simple build tool for JavaScript

jsbuild is a simple build tool for JavaScript projects. It is designed to
work with my workflow, but I hope it can be useful to others as well.

Instead of working with packages like npm, jsbuild uses file imports from JS
Modules. To build a project, you don't need any boilerplate project files.
Pointing jsbuild to a JS file will download any dependencies, build the
project, and output a single JS file.

jsbuild is written in Python as a single `.py` file. You can either install
it through `pip` or just download the file and run it directly.


## Installation through pip

To install jsbuild through pip, run one of the following commands:

    pip3 install js-build-cli

or

    python3 -m pip install js-build-cli

## Installation through download

```sh
curl -o jsbuild https://raw.githubusercontent.com/gkbrk/jsbuild/master/jsbuild.py
chmod +x jsbuild
```

After downloading the file, you can run it directly or add it to your PATH.

    ./jsbuild --help

or

    cp jsbuild /usr/bin/jsbuild
    jsbuild --help

or

    cp jsbuild ~/.local/bin/jsbuild
    jsbuild --help

## Usage

You can run `jsbuild --help` to see the available commands. The most important
command is `build`, which builds the project.

## Requirements

jsbuild requires Python 3 and Java. Depending on the functionality you use,
you may need to install additional command line tools as well.

## License

jsbuild is licensed under the Apache License 2.0. See the LICENSE file for
details.

## Contributing

Rigth now, the best way to contribute to the project is to use it and report
any issues you find. The more users we have, the more issues we can find and
the better the project will be.

Aside from issues, you can also contribute code and documentation.

Contibutors are expected to sign the [Developer Certificate of Origin]. Feel
free to send patches and pull requests as long they have an indication that
you agree to the DCO.

[Developer Certificate of Origin]: https://developercertificate.org/