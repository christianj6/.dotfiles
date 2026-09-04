require "nvchad.mappings"

-- add yours here

local map = vim.keymap.set

map("n", ";", ":", { desc = "CMD enter command mode" })

-- map("i", "jk", "<ESC>")
-- map({ "n", "i", "v" }, "<C-s>", "<cmd> w <cr>")

-- Jump back: Ctrl-[
map('n', '<leader>[', '<C-o>', { noremap = true, silent = true })

-- Jump forward: Ctrl-]
map('n', '<leader>]', '<C-i>', { noremap = true, silent = true })

-- Window width adjustment
map("n", "<C-,>", "<C-w><", { desc = "Decrease window width" })
map("n", "<C-.>", "<C-w>>", { desc = "Increase window width" })
map("n", "<leader>w=", "<C-w>=", { desc = "Equalize window sizes" })

-- Toggle/hide/focus a named yarepl REPL (yarepl registers <Plug>(yarepl-start-{name})
-- / <Plug>(yarepl-hide-{name}) / <Plug>(yarepl-focus-{name}) for every entry in its
-- `metas` table in plugins/init.lua -- "aider" and "pi" are both registered there).
local function toggle_repl(name)
  -- yarepl names its REPL buffers "#name#N" (counter suffix); bufnr() matches
  -- by vim pattern, so anchor it to that exact shape. A bare name would also
  -- match unrelated buffers (e.g. api.lua).
  local bufnr = vim.fn.bufnr("^#" .. name .. "#\\d\\+$")
  if bufnr == -1 then
    bufnr = vim.fn.bufnr("^#" .. name .. "#$")
  end

  -- Where is it displayed? A restored session can show the buffer in a
  -- window on ANOTHER tab, which must not count as "open here".
  local winid = bufnr ~= -1 and vim.fn.bufwinid(bufnr) or -1
  local in_current_tab = false
  if winid ~= -1 then
    in_current_tab = vim.api.nvim_win_get_tabpage(winid) == vim.api.nvim_get_current_tabpage()
  end

  -- Liveness: a real yarepl REPL is a terminal buffer with a running job.
  -- A session-restored zombie has the NAME but no job (persistence/mksession
  -- restores the buffer, not the process), which used to leave ctrl-a
  -- toggling a ghost window on an unfocused tab forever.
  local is_live = false
  if bufnr ~= -1 and vim.bo[bufnr].buftype == "terminal" then
    local job = vim.b[bufnr].terminal_job_id
    if type(job) == "number" and job > 0 then
      pcall(function()
        is_live = vim.fn.jobwait({ job }, 0)[1] == -1
      end)
    end
  end

  if winid ~= -1 and in_current_tab then
    -- Visible here: toggle hide (leave terminal/insert first if needed)
    if vim.api.nvim_get_current_win() == winid then
      local mode = vim.api.nvim_get_mode().mode
      if mode == "t" or mode == "i" then
        vim.cmd("stopinsert")
      end
      vim.defer_fn(function()
        vim.fn.feedkeys(vim.api.nvim_replace_termcodes("<Plug>(yarepl-hide-" .. name .. ")", true, false, true), "")
      end, 10)
    else
      vim.fn.feedkeys(vim.api.nvim_replace_termcodes("<Plug>(yarepl-hide-" .. name .. ")", true, false, true), "")
    end
    return
  end

  if is_live then
    -- Alive: the float may be hidden (no window) or shown on another tab.
    -- Hidden -> yarepl-focus re-opens the float window; other tab -> jump.
    if winid ~= -1 then
      vim.api.nvim_set_current_win(winid)
      vim.cmd("startinsert")
    else
      vim.fn.feedkeys(vim.api.nvim_replace_termcodes("<Plug>(yarepl-focus-" .. name .. ")", true, false, true), "")
      vim.defer_fn(function()
        local repl_win = vim.fn.bufwinid(bufnr)
        if repl_win ~= -1 then
          vim.api.nvim_set_current_win(repl_win)
          vim.cmd("startinsert")
        end
      end, 50)
    end
    return
  end

  -- Zombie: close any windows showing it (possibly on other tabs), delete
  -- the buffer, and start a fresh REPL here.
  if bufnr ~= -1 then
    for _, w in ipairs(vim.fn.win_findbuf(bufnr)) do
      pcall(vim.api.nvim_win_close, w, true)
    end
    pcall(vim.api.nvim_buf_delete, bufnr, { force = true })
  end
  vim.fn.feedkeys(vim.api.nvim_replace_termcodes("<Plug>(yarepl-start-" .. name .. ")", true, false, true), "")
  vim.defer_fn(function()
    local new_bufnr = vim.fn.bufnr("^#" .. name .. "#\\d\\+$")
    local repl_win = new_bufnr ~= -1 and vim.fn.bufwinid(new_bufnr) or -1
    if repl_win ~= -1 then
      vim.api.nvim_set_current_win(repl_win)
      vim.cmd("startinsert")
    end
  end, 100)
end

-- Default REPL for the primary toggle keymap. Change to "aider" to swap
-- which tool <C-a> controls; aider stays reachable via <leader>a regardless.
local DEFAULT_REPL = "pi"

-- Primary REPL toggle keymap (follows DEFAULT_REPL)
map("n", "<C-a>", function() toggle_repl(DEFAULT_REPL) end, { desc = "Toggle default REPL (" .. DEFAULT_REPL .. ")" })
map("t", "<C-a>", function() toggle_repl(DEFAULT_REPL) end, { desc = "Toggle default REPL (" .. DEFAULT_REPL .. ")" })

-- Explicit aider access, independent of DEFAULT_REPL
map("n", "<leader>a", function() toggle_repl("aider") end, { desc = "Toggle aider REPL" })

-- Build script shortcut 
-- map("n", "<leader>b", function ()
--   local dir vim.fn.expand("%:p:h")
--   local output = vim.fn.systemlist("./build.sh")
--   vim.cmd("botright new")
--   vim.api.nvim_buf_set_lines(0, 0, -1, false, output)
--   vim.bo.buftype = "nofile"
--   vim.bo.bufhidden = "wipe"
--   vim.bo.swapfile = false
--   vim.bo.readonly = true
--   vim.bo.filetype = "output"
--
--   map("n", "q", "<cmd>bd!<CR>", {buffer=true})
-- end, {desc="Run build.sh"}
-- )

map("n", "<leader>b", function()
  -- Open a new buffer in a bottom split
  vim.cmd("botright new")
  local buf = vim.api.nvim_get_current_buf()
  vim.api.nvim_buf_set_name(buf, "Build Output")

  -- Make the buffer scratch-like
  vim.bo[buf].buftype = "nofile"
  vim.bo[buf].bufhidden = "wipe"
  vim.bo[buf].swapfile = false
  vim.bo[buf].readonly = false -- temporarily allow writing output
  vim.bo[buf].filetype = "output"

  -- Clear buffer initially
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, {})

  -- Helper: append line and scroll
  local function append_lines(lines)
    local line_count = vim.api.nvim_buf_line_count(buf)
    vim.api.nvim_buf_set_lines(buf, line_count, line_count, false, lines)
    vim.api.nvim_win_set_cursor(0, { vim.api.nvim_buf_line_count(buf), 0 })
  end

  -- Start the job asynchronously
  vim.fn.jobstart("./build.sh", {
    stdout_buffered = false,
    stderr_buffered = false,
    on_stdout = function(_, data, _)
      if data then append_lines(data) end
    end,
    on_stderr = function(_, data, _)
      if data then append_lines(data) end
    end,
    on_exit = function(_, code, _)
      append_lines({ "", "-- DONE (exit code: " .. code .. ") --" })
      vim.bo[buf].readonly = true -- lock the buffer after completion
    end,
  })

  -- Map 'q' to close the output window
  vim.keymap.set("n", "q", "<cmd>bd!<CR>", { buffer = buf, silent = true })
end, { desc = "Run build.sh (live)" })

-- Debugger mappings
map("n", "<leader>db", "<cmd>DapToggleBreakpoint<CR>", { desc = "Toggle breakpoint" })
map("n", "<leader>dc", "<cmd>DapContinue<CR>", { desc = "Continue debugging" })
map("n", "<leader>ds", "<cmd>DapTerminate<CR>", { desc = "Stop debugging" })
map("n", "<leader>dpr", function()
  require('dap-python').test_method()
end, { desc = "Run Python test method" })

-- Copy to clipboard
map("v", "<leader>y", "\"+y", { desc = "Copy selection to clipboard" })
map("n", "<leader>Y", "\"+yg_", { desc = "Copy line without newline to clipboard" })
map("n", "<leader>y", "\"+y", { desc = "Copy to clipboard" })
map("n", "<leader>yy", "\"+yy", { desc = "Copy line to clipboard" })

-- Paste from clipboard
map("n", "<leader>p", "\"+p", { desc = "Paste from clipboard after cursor" })
map("n", "<leader>P", "\"+P", { desc = "Paste from clipboard before cursor" })
map("v", "<leader>p", "\"+p", { desc = "Paste from clipboard after selection" })
map("v", "<leader>P", "\"+P", { desc = "Paste from clipboard before selection" })

-- map("n", "<Leader>as", "<Plug>(REPLStart-aider)", { desc = "Start an aider REPL" })
-- map("n", "<Leader>af", "<Plug>(REPLFocus-aider)", { desc = "Focus on aider REPL" })
-- map("n", "<Leader>ah", "<Plug>(REPLHide-aider)", { desc = "Hide aider REPL" })
-- map("v", "<Leader>ar", "<Plug>(REPLSendVisual-aider)", { desc = "Send visual region to aider" })
-- map("n", "<Leader>arr", "<Plug>(REPLSendLine-aider)", { desc = "Send lines to aider" })
-- map("n", "<Leader>ar", "<Plug>(REPLSendOperator-aider)", { desc = "Send Operator to aider" })
