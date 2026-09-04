-- load defaults i.e lua_lsp
require("nvchad.configs.lspconfig").defaults()

-- EXAMPLE
local servers = { "html", "cssls", "terraformls", "markdown_oxide", "pyright", "clangd", "svelte" }

-- lsps with default config: nvchad.configs.lspconfig's defaults() already
-- applies capabilities/on_init to every server via vim.lsp.config("*", ...)
-- and wires on_attach through an LspAttach autocmd, so enabling by name is
-- all that's needed -- nvim-lspconfig ships each server's cmd/filetypes/
-- root_markers as lsp/<name>.lua, auto-loaded by vim.lsp.enable. (The old
-- require("lspconfig")[lsp].setup{} "framework" is deprecated, removed in
-- nvim-lspconfig v3.0.0.)
vim.lsp.enable(servers)

-- When a conda env is active (the shell env seam guarantees it in marked
-- project dirs), analyze against that env's interpreter so the LSP sees the
-- exact python the project runs on. No CONDA_PREFIX -> stock behavior.
if vim.env.CONDA_PREFIX and vim.env.CONDA_PREFIX ~= "" then
  vim.lsp.config("pyright", {
    settings = {
      python = {
        pythonPath = vim.env.CONDA_PREFIX .. "/bin/python",
      },
    },
  })
end

-- configuring a single server beyond its shipped defaults, example: lua_ls
-- vim.lsp.config("ts_ls", { settings = {} })
-- vim.lsp.enable("ts_ls")
