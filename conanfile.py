from io import StringIO
import os, shutil, platform
from conans import ConanFile, tools, AutoToolsBuildEnvironment

class GlibConan(ConanFile):
    name = 'glib'

    version = '2.55.2'
    sha = 'd06830c28b0d3e8c4f1fbb6d1e359a8c76dafa0f6f2413727846e98a9d0b41aa'

    requires = (
        'ffi/3.2.1@ntc/stable',
        'zlib/1.2.11/conan@stable',
        'helpers/[>=0.1.0]@ntc/stable',
    )
    settings = 'os', 'compiler', 'build_type', 'arch'
    url = 'https://github.com/vuo/conan-glib'
    license = 'https://developer.gnome.org/glib/stable/glib.html'
    description = 'Core application building blocks for GNOME libraries and applications'
    exports = 'config.*.cache'
    build_requires = 'pkg-config/0.29.2@ntc/stable'

    @property
    def host_is_arm(self):
        return self.settings.get_safe('arch') and self.settings.get_safe('arch').startswith('arm')

    @property
    def target_mach(self):
        return os.environ.get('TARGETMACH', self.settings.get_safe('arch'))

    def source(self):
        # url = 'https://download.gnome.org/sources/glib/2.51/glib-%s.tar.xz'%self.source_version
        url = f'https://github.com/GNOME/glib/archive/{self.version}.tar.gz'
        filename = os.path.basename(url)
        tools.download(url, filename)
        tools.check_sha256(filename, self.sha)
        tools.unzip(filename)
        shutil.move(f'glib-{self.version}', self.name)
        os.unlink(filename)

    def imports(self):
        self.copy(pattern='*.dylib', dst=self.name, src='lib')

    def build(self):
        with tools.chdir(self.name):
            autotools = AutoToolsBuildEnvironment(self)
            autotools.flags.append('-O2')
            if 'Darwin' == platform.system():
                autotools.flags.append('-mmacosx-version-min=10.10')
            autotools.link_flags.append('-Wl,-rpath,@loader_path')
            autotools.link_flags.append('-Wl,-rpath,@loader_path/../..')

            env_vars = {}
            pkg_config_path = []

            # libffi
            env_vars['PKG_CONFIG_LIBFFI_PREFIX'] = tweakPath(self.deps_cpp_info['ffi'].rootpath)
            pkg_config_path.append(os.path.join(self.deps_cpp_info['ffi'].rootpath, 'lib', 'pkgconfig'))

            # zlib
            env_vars['PKG_CONFIG_ZLIB_PREFIX'] = tweakPath(self.deps_cpp_info['zlib'].rootpath)
            pkg_config_path.append(self.deps_cpp_info['zlib'].rootpath)

            env_vars['PKG_CONFIG_PATH'] = joinPaths( list(map(adjustPath, pkg_config_path)) )

            # This seems redundant, but happens to be required despite the
            # pkg-config above
            with tools.environment_append(env_vars):
                output = StringIO()
                self.run('pkg-config --libs-only-L libffi', output)

                # Assuming only one libpath
                libpath = str(output.getvalue()).strip().replace('-L', '-Wl,-rpath -Wl,')

                # env_vars['LDFFI_LIBS'] = str(output.getvalue()).strip()
                env_vars['LDFLAGS'] = libpath


            s = 'Environment:\n'
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
            args.append(f'--prefix={self.package_folder}')

            self.output.info('Configure arguments: %s'%' '.join(args))

            with tools.environment_append(env_vars):
                self.run('./autogen.sh %s'%' '.join(args))

                autotools.make(args=['install'])


    def package_info(self):
        self.cpp_info.libs = ['glib']

# vim: ts=4 sw=4 expandtab ffs=unix ft=python foldmethod=marker :
