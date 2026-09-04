return {
  {
    "stevearc/conform.nvim",
    -- event = 'BufWritePre', -- uncomment for format on save
    opts = require "configs.conform",
  },

  -- These are some examples, uncomment them if you want to see them work!
  {
    "neovim/nvim-lspconfig",
    config = function()
      require "configs.lspconfig"
    end,
  },

  {
      "kdheepak/lazygit.nvim",
      lazy = true,
      cmd = {
          "LazyGit",
          "LazyGitConfig",
          "LazyGitCurrentFile",
          "LazyGitFilter",
          "LazyGitFilterCurrentFile",
      },
      -- optional for floating window border decoration
      dependencies = {
          "nvim-lua/plenary.nvim",
      },
      -- setting the keybinding for LazyGit with 'keys' is recommended in
      -- order to load the plugin when the command is run for the first time
      keys = {
          { "<leader>lg", "<cmd>LazyGit<cr>", desc = "LazyGit" }
      }
  },

  {
    'jmbuhr/otter.nvim',
    lazy = false,
    dependencies = {
      'nvim-treesitter/nvim-treesitter',
    },
    opts = {},
  },

  {
    "sphamba/smear-cursor.nvim",
    lazy = true,
    opts = {},
  },

  {
      "kylechui/nvim-surround",
      version = "*", -- Use for stability; omit to use `main` branch for the latest features
      event = "VeryLazy",
      config = function()
          require("nvim-surround").setup({
              -- Configuration here, or leave empty to use defaults
          })
      end
  },

  {
    "nvim-tree/nvim-tree.lua",
    opts = {
      view = {
        preserve_window_proportions = true,
        adaptive_size = true
      },
      git = {
        timeout = 600
      }
    },
  },

  {
    'akinsho/toggleterm.nvim',
    lazy = false,
    version = "*",
    opts = {
      open_mapping = [[<C-o>]],
      direction = 'float'
    }
  },

  {
    "folke/persistence.nvim",
    lazy = false, -- auto-restore must fire on a bare `nvim` start (the herdr
                  -- guard opens nvim with no file args, so BufReadPre never fires)
    config = function(_, opts)
      require("persistence").setup(opts)
      -- persistence saves sessions on exit but does not autoload; restore
      -- the current directory's session on a bare `nvim` start (no file
      -- args) -- the shape herdr-restored panes open with. `nvim somefile`
      -- stays a focused single-file edit.
      vim.api.nvim_create_autocmd("VimEnter", {
        nested = true,
        callback = function()
          if vim.fn.argc() == 0 then
            require("persistence").load()
          end
        end,
      })
    end,
  },

  {
    "milanglacier/yarepl.nvim",
    config = function()
      -- yarepl's own default float window (utility.lua's default_float_wincmd)
      -- anchors `relative = "laststatus"` with row/col offset by half the
      -- window's own size, which lands the float in the bottom-right corner
      -- instead of the middle of the screen. This is the same look (50%
      -- width, 70% height, rounded border) with real editor-relative centering.
      local function centered_float_wincmd(config_getter)
        return function(bufnr, name)
          local width = math.floor(vim.o.columns * 0.5)
          local height = math.floor(vim.o.lines * 0.7)
          local winid = vim.api.nvim_open_win(bufnr, true, {
            relative = "editor",
            row = math.floor((vim.o.lines - height) / 2),
            col = math.floor((vim.o.columns - width) / 2),
            width = width,
            height = height,
            style = "minimal",
            title = name,
            border = "rounded",
            title_pos = "center",
          })
          if config_getter().show_winbar_in_float_window then
            vim.wo[winid].winbar = "%t"
          end
        end
      end

      -- yarepl's pi extension defaults to running the `pi` binary; this
      -- machine's agent is named `omp`, launched via the omp-last wrapper
      -- (scripts/projects/omp-last) so ctrl-a re-attaches the project's
      -- most recent omp session instead of starting a fresh conversation.
      local pi_ext = require('yarepl.extensions.pi')
      local aider_ext = require('yarepl.extensions.aider')
      pi_ext.setup({ pi_cmd = 'omp-last', wincmd = centered_float_wincmd(function() return pi_ext.config end) })
      aider_ext.setup({ wincmd = centered_float_wincmd(function() return aider_ext.config end) })

      require("yarepl").setup({
        scratch_repl = true,
        extensions = { "aider", "pi" },
        metas = {
          aider = aider_ext.create_aider_meta(),
          pi = pi_ext.create_pi_meta(),
        },
        meta = {
          split = "horizontal",
          height = 15,
        },
      })
    end,
    dependencies = {
      "nvim-treesitter/nvim-treesitter",
    },
    lazy = false, -- optional: force early loading for mappings to work
  },

  {
    "rcarriga/nvim-dap-ui",
    dependencies = "mfussenegger/nvim-dap",
    config = function()
      local dap = require("dap")
      local dapui = require("dapui")
      dapui.setup()
      dap.listeners.after.event_initialized["dapui_config"] = function()
        dapui.open()
      end
      dap.listeners.before.event_terminated["dapui_config"] = function()
        dapui.close()
      end
      dap.listeners.before.event_exited["dapui_config"] = function()
        dapui.close()
      end
    end
  },
  {
    "mfussenegger/nvim-dap",
    -- config = function(_, opts)
    --   require("core.utils").load_mappings("dap")
    -- end
  },
  {
    "mfussenegger/nvim-dap-python",
    ft = "python",
    dependencies = {
      "mfussenegger/nvim-dap",
      "rcarriga/nvim-dap-ui",
      "nvim-neotest/nvim-nio",
    },
    config = function(_, opts)
      -- local path = "~/.local/share/nvim/mason/packages/debugpy/venv/bin/python"
      local conda_prefix = os.getenv("CONDA_PREFIX")
      local python_path = conda_prefix and (conda_prefix .. "/bin/python") or "~/.local/share/nvim/mason/packages/debugpy/venv/bin/python"

      require("dap-python").setup(path)
      -- require("core.utils").load_mappings("dap_python")
    end,
  },
  {
     "m4xshen/hardtime.nvim",
     -- lazy = false,
     dependencies = { "MunifTanjim/nui.nvim" },
     opts = {},
  },
  {
    -- `mason.nvim` itself has no `ensure_installed` option; that only
    -- exists on mason-tool-installer (or mason-lspconfig, for LSP servers
    -- specifically). Without it these tools silently never auto-install.
    "WhoIsSethDaniel/mason-tool-installer.nvim",
    -- NvChad's lazy.nvim defaults are `lazy = true` (configs/lazy.lua); this
    -- has no event/cmd/ft trigger, so without `lazy = false` it would sit
    -- installed but never call setup(), and ensure_installed would never run.
    lazy = false,
    dependencies = { "williamboman/mason.nvim" },
    opts = {
      ensure_installed = {
        "black",
        "debugpy",
        "mypy",
        "ruff",
        "pyright",
        "stylua",
        "clangd",
      },
    },
  },
  {
    "mistweaverco/kulala.nvim",
    ft = { "http", "rest" },
    opts = {
      global_keymaps = true,
      global_keymaps_prefix = "<leader>k",
      kulala_keymaps_prefix = "",
      ui = {
        display_mode = "split",
        win_opts = {
          width = 80,
          height = 20,
          -- split = "vertical",
        },
      }
    },
  },
  {
  	"nvim-treesitter/nvim-treesitter",
  	opts = {
  		ensure_installed = {
  			"vim", "lua", "vimdoc",
       "html", "css", "python", "http"
  		},
  	},
  },
}
