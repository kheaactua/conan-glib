from io import StringIO
import os, shutil, platform, re
from conans import ConanFile, tools, AutoToolsBuildEnvironment

class GlibConan(ConanFile):
    name           = 'glib'
    version        = '2.55.2'
    sha            = 'd06830c28b0d3e8c4f1fbb6d1e359a8c76dafa0f6f2413727846e98a9d0b41aa'
    settings       = 'os', 'compiler', 'build_type', 'arch', 'arch_build'
    url            = 'https://github.com/vuo/conan-glib'
    license        = 'https://developer.gnome.org/glib/stable/glib.html'
    description    = 'Core application building blocks for GNOME libraries and applications'
    exports        = 'config.*.cache'
    build_requires = 'pkg-config/0.29.2@ntc/stable'

    requires = (
        'ffi/3.2.1@ntc/stable',
        'zlib/1.2.11@conan/stable',
        'helpers/[>=0.2.0]@ntc/stable',
    )

    @property
    def host_is_arm(self):
        return self.settings.get_safe('arch') and self.settings.get_safe('arch').startswith('arm')

    @property
    def target_mach(self):
        return os.environ.get('TARGETMACH', self.settings.get_safe('arch'))

    def source(self):
        url = 'https://github.com/GNOME/glib/archive/{version}.tar.gz'.format(version=self.version)
        filename = os.path.basename(url)
        tools.download(url, filename)
        tools.check_sha256(filename, self.sha)
        tools.unzip(filename)
        shutil.move('glib-%s'%self.version, self.name)
        os.unlink(filename)

    def imports(self):
        self.copy(pattern='*.dylib', dst=self.name, src='lib')

    def build(self):
        from platform_helpers import adjustPath, appendPkgConfigPath

        with tools.chdir(self.name):
            autotools = AutoToolsBuildEnvironment(self, win_bash=tools.os_info.is_windows)
            autotools.flags.append('-O2')
            if 'Darwin' == platform.system():
                autotools.flags.append('-mmacosx-version-min=10.10')
            autotools.link_flags.append('-Wl,-rpath,@loader_path')
            autotools.link_flags.append('-Wl,-rpath,@loader_path/../..')

            env_vars = {}
            pkg_config_path = []

            # zlib
            env_vars['PKG_CONFIG_ZLIB_PREFIX'] = adjustPath(self.deps_cpp_info['zlib'].rootpath)
            pkg_config_path.append(self.deps_cpp_info['zlib'].rootpath)

            appendPkgConfigPath(
                list(map(adjustPath, pkg_config_path)),
                env_vars
            )

            # This seems redundant, but happens to be required despite the
            # pkg-config above
            with tools.environment_append(env_vars):
                output = StringIO()
                self.run('pkg-config --libs-only-L libffi', output)

                # Assuming only one libpath
                libpath = str(output.getvalue()).strip().replace('-L', '-Wl,-rpath -Wl,')
                env_vars['LDFLAGS'] = libpath

            s = 'Selected variables from the environment:\n'
            for k,v in os.environ.items():
                if re.search('PKG_', k):
                    s += ' - %s = %s\n'%(k, v)
            self.output.info(s)

            s = 'Additional environment:\n'
            for k,v in env_vars.items():
                s += ' - %s = %s\n'%(k, v)
            self.output.info(s)

            args = []
            arch_options_cache_file = os.path.join(self.build_folder, 'config.%s.cache'%self.target_mach)
            if os.path.exists(arch_options_cache_file):
                args.append('--host=%s'%self.target_mach)
                args.append('--cache-file=' + arch_options_cache_file)

            args.append('--quiet')
            args.append('--without-pcre')
            args.append('--disable-fam')
            args.append('--disable-dependency-tracking')
            args.append('--enable-static')
            args.append('--enable-included-printf')
            args.append('--enable-libmount=no')
            args.append('--prefix=%s'%self.package_folder)

            self.output.info('Configure arguments: %s'%' '.join(args))

            with tools.environment_append(env_vars):
                self.run('./autogen.sh %s'%' '.join(args), win_bash=tools.os_info.is_windows)
                autotools.make(args=['install'])

    def package_info(self):
        self.cpp_info.libs = ['glib']

        # Populate the pkg-config environment variables
        with tools.pythonpath(self):
            from platform_helpers import adjustPath, appendPkgConfigPath
            self.env_info.PKG_CONFIG_GLIB_2_0_PREFIX = self.package_folder
            appendPkgConfigPath(os.path.join(self.package_folder, 'lib', 'pkgconfig'), self.env_info)

# vim: ts=4 sw=4 expandtab ffs=unix ft=python foldmethod=marker :
