#!/usr/bin/env python
# -*- coding: utf-8 -*-

from io import StringIO
import os, shutil
from conans import ConanFile, tools, AutoToolsBuildEnvironment
from conans.errors import ConanException

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

    def build_requirements(self):
        pack_names = None
        if 'ubuntu' == tools.os_info.linux_distro:
            pack_names = ['autoconf', 'autopoint', 'automake', 'autotools-dev', 'libtool', 'autopoint', 'gtk-doc-tools']

            if self.settings.arch == 'x86':
                full_pack_names = []
                for pack_name in pack_names:
                    full_pack_names += [pack_name + ':i386']
                pack_names = full_pack_names

        if pack_names:
            installer = tools.SystemPackageTool()
            try:
                installer.update() # Update the package database
                installer.install(' '.join(pack_names)) # Install the package
            except ConanException:
                self.output.warn('Could not run build requirements installer.  Required packages might be missing.')

    def source(self):
        archive_ext = 'tar.gz'
        cached_archive_name = 'glib-' + str(self.version) + '.' + archive_ext

        from source_cache import copyFromCache
        if not copyFromCache(cached_archive_name):
            archive_file = str(self.version) + '.' + archive_ext
            url = 'https://github.com/GNOME/glib/archive/{archive_file}'.format(archive_file=archive_file)
            tools.download(url, cached_archive_name)
            tools.check_sha256(cached_archive_name, self.sha)

        tools.unzip(cached_archive_name)
        shutil.move('glib-%s'%self.version, self.name)
        os.unlink(cached_archive_name)

    def imports(self):
        self.copy(pattern='*.dylib', dst=self.name, src='lib')

    def build(self):
        from platform_helpers import adjustPath, prependPkgConfigPath

        with tools.chdir(self.name):
            autotools = AutoToolsBuildEnvironment(self, win_bash=tools.os_info.is_windows)
            autotools.flags.append('-O2')
            if tools.os_info.is_macos:
                autotools.flags.append('-mmacosx-version-min=10.10')
            autotools.link_flags.append('-Wl,-rpath,@loader_path')
            autotools.link_flags.append('-Wl,-rpath,@loader_path/../..')

            env_vars = {}
            pkg_config_path = []

            # zlib
            env_vars['PKG_CONFIG_ZLIB_PREFIX'] = adjustPath(self.deps_cpp_info['zlib'].rootpath)
            pkg_config_path.append(self.deps_cpp_info['zlib'].rootpath)

            prependPkgConfigPath(
                list(map(adjustPath, pkg_config_path)),
                env_vars
            )

            # This seems redundant, but happens to be required despite the
            # pkg-config above
            # Note: tools.environment_append() writes to env_vars, so for
            #       safety we send in a copy
            env_vars_copy = dict(env_vars)
            with tools.environment_append(env_vars_copy):
                libpaths = []
                for p in ['libffi', 'zlib']:
                    output = StringIO()
                    self.run('pkg-config --libs-only-L %s'%p, output)
                    libpaths.extend(str(output.getvalue()).strip().split('-L'))

                while '' in libpaths: libpaths.remove('')

                # Extending autotools.link_flags with these flags doesn't seem
                # to work, I still get a linker error in the install target
                sep = '-Wl,-rpath -Wl,'
                env_vars['LDFLAGS'] = ' '.join(list(map(lambda s: sep+s, libpaths)))

            s = 'Selected variables from the environment:\n'
            for k,v in os.environ.items():
                s += ' - %s = %s\n'%(k, v)
            self.output.info(s)

            s  = 'Additional environment:\n'
            ps = 'Additional pkg-config environment:\n'
            for k,v in env_vars.items():
                if 'PKG_' in k:
                    if not k == 'PKG_CONFIG_PATH':
                        ps += ' - %s = %s\n'%(k, v)
                else:
                    s  += ' - %s = %s\n'%(k, v)
            self.output.info(s)
            ps += ' - PKG_CONFIG_PATH:\n  - ' + '\n  - '.join(env_vars['PKG_CONFIG_PATH'])
            self.output.info(ps)

            self.output.info('Additional Library Paths:\n - %s'%'\n - '.join(autotools.library_paths))
            self.output.info('Additional Linker Flags:\n - %s'%'\n - '.join(autotools.link_flags))
            if 'LDFLAGS' in env_vars:
                self.output.info('Additional Linker Flags in Environment:\n - %s'%env_vars['LDFLAGS'])

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
        # Using collect_libs results in a warning about similar libs with
        # different file extensions.
        self.cpp_info.libs = ['glib']

        # Populate the pkg-config environment variables
        with tools.pythonpath(self):
            from platform_helpers import appendPkgConfigPath
            self.env_info.PKG_CONFIG_GLIB_2_0_PREFIX = self.package_folder
            appendPkgConfigPath(os.path.join(self.package_folder, 'lib', 'pkgconfig'), self.env_info)

# vim: ts=4 sw=4 expandtab ffs=unix ft=python foldmethod=marker :
