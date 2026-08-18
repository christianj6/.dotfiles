-- Neovim 0.12.x crashes highlighting any markdown buffer that has a fenced
-- code block:
--   attempt to call method 'range' (a nil value)
-- from vim/treesitter/languagetree.lua:215, reproducible with `nvim --clean`
-- (not specific to this config or to nvim-treesitter). Traced to
-- LanguageTree:_get_injections()'s get_node_ranges() calling
-- vim.treesitter.get_range() on a nil node while resolving markdown's
-- `injections.scm` match that injects a fenced code block's own language
-- parser into its content:
--   (fenced_code_block
--     (info_string (language) @injection.language)
--     (code_fence_content) @injection.content)
-- Confirmed empirically (by clearing this pattern and nothing else) that
-- this specific pattern is the trigger -- a plain markdown file with no
-- fenced code block never crashes, and overriding the `highlights` query
-- (including the `conceal_lines` directive named in the upstream reports
-- below) does not stop it, so it isn't fixable at that level either.
-- Upstream: https://github.com/neovim/neovim/issues/39032
--           https://github.com/nvim-treesitter/nvim-treesitter/issues/8618
--
-- Fix: override the `injections` query for markdown with everything except
-- that one pattern (html/yaml-frontmatter/toml-frontmatter/markdown_inline
-- injection all stay intact). Unlike disabling treesitter for markdown
-- outright, this keeps real treesitter highlighting for headings, lists,
-- emphasis, etc. -- fenced code blocks just fall back to plain
-- `@markup.raw.block` coloring instead of their own language's syntax
-- colors. query.set() is a global, immediate, in-memory override, so this
-- applies no matter what triggers markdown treesitter (opening a file,
-- an LSP hover/floating preview, etc.) -- no FileType-autocmd timing to
-- get right.
--
-- Remove this once the bug is fixed upstream in the Neovim version this
-- machine runs.
vim.treesitter.query.set("markdown", "injections", [[
((html_block) @injection.content
  (#set! injection.language "html")
  (#set! injection.combined)
  (#set! injection.include-children))

((minus_metadata) @injection.content
  (#set! injection.language "yaml")
  (#offset! @injection.content 1 0 -1 0)
  (#set! injection.include-children))

((plus_metadata) @injection.content
  (#set! injection.language "toml")
  (#offset! @injection.content 1 0 -1 0)
  (#set! injection.include-children))

([
  (inline)
  (pipe_table_cell)
] @injection.content
  (#set! injection.language "markdown_inline"))
]])
