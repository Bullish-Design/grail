{ pkgs, lib, config, inputs, ... }:

{
  # https://devenv.sh/basics/
  env.GREET = "devenv";

  # https://devenv.sh/packages/
  packages = [ 
    pkgs.git 
    pkgs.uv
    ];

  # https://devenv.sh/languages/
  # languages.rust.enable = true;
  languages = {
      python = {
          enable = true;
          version = "3.13";
          venv.enable = true;
          uv.enable = true;
        };
    };

  # https://devenv.sh/processes/
  # processes.cargo-watch.exec = "cargo-watch";

  # https://devenv.sh/services/
  # services.postgres.enable = true;

  # https://devenv.sh/scripts/
  scripts.hello.exec = ''
    echo hello from $GREET
  '';

  # devman — the automation plane (CONCEPT.md §5). `base` alone: this repository
  # ships no scheduled work and writes none of its own files.
  devman = {
    enable = true;
    project = "grail";
    groups = [ "base" ];
  };

  # https://devenv.sh/tasks/
  #
  # The two task names the `base` group calls (groups/base/README.md). devenv
  # owns each implementation; Dagu owns the composition (§6). `uv run` rather
  # than bare names: the venv bin is on the interactive shell's PATH but not on
  # the task runner's PATH (STAGE_7_LOG.md, wave 2b). `ruff check src tests`
  # matches the repo's own scope; the tree carries 83 findings there today
  # (recorded, not repaired — adoption and repair are separate passes).
  tasks = {
    "grail:lint".exec = "uv run ruff check src tests";
    "grail:test".exec = "uv run pytest";

    "base:check".after = [ "grail:lint" ];
    "base:test".after = [ "grail:test" ];
  };

  enterShell = ''
    hello
    git --version
  '';

  # https://devenv.sh/tasks/
  # tasks = {
  #   "myproj:setup".exec = "mytool build";
  #   "devenv:enterShell".after = [ "myproj:setup" ];
  # };

  # https://devenv.sh/tests/
  enterTest = ''
    echo "Running tests"
    git --version | grep --color=auto "${pkgs.git.version}"
  '';

  # https://devenv.sh/pre-commit-hooks/
  # pre-commit.hooks.shellcheck.enable = true;

  # See full reference at https://devenv.sh/reference/options/
}
