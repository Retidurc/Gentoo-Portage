# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

import portage
from portage.const import USER_CONFIG_PATH
from portage.package.ebuild.config import config
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class CcacheLateExpandTestCase(TestCase):
    _ebuilds = {
        "dev-libs/A-1": {"EAPI": "8", "SLOT": "0"},
        "dev-libs/B-1": {"EAPI": "8", "SLOT": "0"},
    }

    def _make_playground(self, make_conf, package_env=None):
        user_config = {"make.conf": make_conf}
        if package_env is not None:
            user_config["package.env"] = package_env

        playground = ResolverPlayground(
            ebuilds=self._ebuilds,
            user_config=user_config,
        )

        # Keep FEATURES=ccache from being removed due to a missing
        # masquerade directory.
        os.makedirs(
            os.path.join(playground.eprefix, "usr", "lib", "ccache", "bin"),
            exist_ok=True,
        )
        return playground

    @staticmethod
    def _get_settings(playground):
        settings = config(clone=playground.settings)
        root_config = playground.trees[playground.eroot]["root_config"]
        portdb = root_config.trees["porttree"].dbapi
        return settings, portdb

    @staticmethod
    def _prepare(settings, portdb, cpv, phase="setup"):
        ebuild_path = portdb.findname(cpv)
        settings.setcpv(cpv, mydb=portdb)
        portage.doebuild_environment(
            ebuild_path,
            phase,
            settings=settings,
            db=portdb,
        )

    def testLateExpandAndPackageEnvPriority(self):
        make_conf = [
            'FEATURES="${FEATURES} ccache"',
            'CCACHE_NAMESPACE="${CATEGORY}/${PN}"',
            'CCACHE_STATSLOG="${T}/ccache.statslog"',
            'CCACHE_LOGFILE="${T}/ccache.log"',
            'DISTCC_DIR="${T}/distcc"',
        ]
        playground = self._make_playground(
            make_conf,
            package_env=["dev-libs/B b"],
        )
        try:
            env_dir = os.path.join(
                playground.eprefix,
                USER_CONFIG_PATH,
                "env",
            )
            os.makedirs(env_dir, exist_ok=True)
            with open(os.path.join(env_dir, "b"), "w") as f:
                f.write('CCACHE_NAMESPACE="override-${PN}"\n')

            settings, portdb = self._get_settings(playground)

            self.assertEqual(settings["CCACHE_NAMESPACE"], "${CATEGORY}/${PN}")
            self.assertEqual(settings["CCACHE_STATSLOG"], "${T}/ccache.statslog")
            self.assertEqual(settings["DISTCC_DIR"], "${T}/distcc")

            self._prepare(settings, portdb, "dev-libs/A-1")
            self.assertEqual(settings["CCACHE_NAMESPACE"], "dev-libs/A")
            self.assertEqual(
                settings["CCACHE_STATSLOG"],
                os.path.join(settings["T"], "ccache.statslog"),
            )
            self.assertEqual(
                settings["CCACHE_LOGFILE"],
                os.path.join(settings["T"], "ccache.log"),
            )
            self.assertEqual(
                settings["DISTCC_DIR"],
                os.path.join(settings["T"], "distcc"),
            )

            self._prepare(settings, portdb, "dev-libs/B-1")
            self.assertEqual(settings["CCACHE_NAMESPACE"], "override-B")
            self.assertEqual(
                settings["CCACHE_STATSLOG"],
                os.path.join(settings["T"], "ccache.statslog"),
            )
        finally:
            playground.cleanup()

    def testCompilerCheckCommand(self):
        playground = self._make_playground(
            [
                'FEATURES="${FEATURES} ccache"',
                'PORTAGE_CCACHE_COMPILERCHECK_COMMAND="printf 7.1.2"',
            ]
        )
        try:
            settings, portdb = self._get_settings(playground)
            self._prepare(settings, portdb, "dev-libs/A-1")
            self.assertEqual(settings["CCACHE_COMPILERCHECK"], "string:7.1.2")
            self.assertEqual(
                settings.environ()["CCACHE_COMPILERCHECK"],
                "string:7.1.2",
            )
            self.assertNotIn(
                "PORTAGE_CCACHE_COMPILERCHECK_COMMAND",
                settings.environ(),
            )

            settings.pop("CCACHE_COMPILERCHECK")
            self._prepare(settings, portdb, "dev-libs/A-1", "compile")
            self.assertEqual(settings["CCACHE_COMPILERCHECK"], "string:7.1.2")
        finally:
            playground.cleanup()

    def testCompilerCheckCommandPackageEnvOverride(self):
        playground = self._make_playground(
            [
                'FEATURES="${FEATURES} ccache"',
                'PORTAGE_CCACHE_COMPILERCHECK_COMMAND="printf base"',
            ],
            package_env=["dev-libs/B b"],
        )
        try:
            env_dir = os.path.join(
                playground.eprefix,
                USER_CONFIG_PATH,
                "env",
            )
            os.makedirs(env_dir, exist_ok=True)
            with open(os.path.join(env_dir, "b"), "w") as f:
                f.write('PORTAGE_CCACHE_COMPILERCHECK_COMMAND="printf override"\n')

            settings, portdb = self._get_settings(playground)
            self._prepare(settings, portdb, "dev-libs/A-1")
            self.assertEqual(settings["CCACHE_COMPILERCHECK"], "string:base")

            settings, portdb = self._get_settings(playground)
            self._prepare(settings, portdb, "dev-libs/B-1")
            self.assertEqual(settings["CCACHE_COMPILERCHECK"], "string:override")
        finally:
            playground.cleanup()

    def testCompilerCheckCommandFirstLine(self):
        playground = self._make_playground(
            [
                'FEATURES="${FEATURES} ccache"',
                'PORTAGE_CCACHE_COMPILERCHECK_COMMAND="printf \'first\\nsecond\\n\'"',
            ]
        )
        try:
            settings, portdb = self._get_settings(playground)
            self._prepare(settings, portdb, "dev-libs/A-1")
            self.assertEqual(settings["CCACHE_COMPILERCHECK"], "string:first")
        finally:
            playground.cleanup()

    def testCompilerCheckExplicit(self):
        playground = self._make_playground(
            [
                'FEATURES="${FEATURES} ccache"',
                'CCACHE_COMPILERCHECK="content"',
                'PORTAGE_CCACHE_COMPILERCHECK_COMMAND="printf 7.1.2"',
            ]
        )
        try:
            settings, portdb = self._get_settings(playground)
            self._prepare(settings, portdb, "dev-libs/A-1")
            self.assertEqual(settings["CCACHE_COMPILERCHECK"], "content")
        finally:
            playground.cleanup()

    def testCompilerCheckCommandWithoutCcache(self):
        playground = self._make_playground(
            [
                'FEATURES="${FEATURES} -ccache"',
                'PORTAGE_CCACHE_COMPILERCHECK_COMMAND="printf 7.1.2"',
            ]
        )
        try:
            settings, portdb = self._get_settings(playground)
            self._prepare(settings, portdb, "dev-libs/A-1")
            self.assertIsNone(settings.get("CCACHE_COMPILERCHECK"))
        finally:
            playground.cleanup()

    def testCompilerCheckCommandPhaseGating(self):
        playground = self._make_playground(
            [
                'FEATURES="${FEATURES} ccache"',
                'PORTAGE_CCACHE_COMPILERCHECK_COMMAND="printf 7.1.2"',
            ]
        )
        try:
            for phase in ("fetch", "depend"):
                with self.subTest(phase=phase):
                    settings, portdb = self._get_settings(playground)
                    self._prepare(settings, portdb, "dev-libs/A-1", phase)
                    self.assertIsNone(settings.get("CCACHE_COMPILERCHECK"))
        finally:
            playground.cleanup()

    def testCompilerCheckCommandFallback(self):
        for command in ("false", "true", "printf 'unterminated"):
            with self.subTest(command=command):
                playground = self._make_playground(
                    [
                        'FEATURES="${FEATURES} ccache"',
                        'PORTAGE_CCACHE_COMPILERCHECK_COMMAND="%s"' % command,
                    ]
                )
                try:
                    settings, portdb = self._get_settings(playground)
                    self._prepare(settings, portdb, "dev-libs/A-1")
                    self.assertIsNone(settings.get("CCACHE_COMPILERCHECK"))
                finally:
                    playground.cleanup()
