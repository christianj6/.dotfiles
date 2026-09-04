-- This file needs to have same structure as nvconfig.lua 
-- https://github.com/NvChad/ui/blob/v3.0/lua/nvconfig.lua
-- Please read that file to know all available options :( 

---@type ChadrcConfig
local M = {}
vim.opt.relativenumber = true

M.base46 = {
	theme = "catppuccin",

	-- hl_override = {
	-- 	Comment = { italic = true },
	-- 	["@comment"] = { italic = true },
	-- },
}

-- M.nvdash = { load_on_startup = true }
-- M.ui = {
--       tabufline = {
--          lazyload = false
--      }
--}

M.ui = {
	statusline = {
		modules = {
			-- Upstream bug (NvChad/ui v3.0, stl/default.lua:50): the `cwd` module
			-- indexes `vim.uv.cwd()` unguarded, so any nvim whose working directory
			-- cannot be resolved (deleted dir, removed worktree, TCC denial) crashes
			-- the statusline on every redraw: "attempt to index local 'name'".
			-- This override is identical except for the nil guard; drop it once
			-- upstream fixes the module.
			cwd = function()
				local sep_l = require("nvchad.stl.utils").separators.default.left
				local icon = "%#St_cwd_icon#" .. "󰉋 "
				local name = vim.uv.cwd()
				local text = name and (name:match "([^/\\]+)[/\\]*$" or name) or "cwd?"
				name = "%#St_cwd_text#" .. " " .. text .. " "
				return (vim.o.columns > 85 and ("%#St_cwd_sep#" .. sep_l .. icon .. name)) or ""
			end,
		},
	},
}

return M
