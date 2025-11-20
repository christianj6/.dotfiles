require "nvchad.mappings"

-- add yours here

local map = vim.keymap.set

map("n", ";", ":", { desc = "CMD enter command mode" })

-- map("i", "jk", "<ESC>")
-- map({ "n", "i", "v" }, "<C-s>", "<cmd> w <cr>")

-- Jump back: Ctrl-[
map('n', '<C-[>', '<C-o>', { noremap = true, silent = true })

-- Jump forward: Ctrl-]
map('n', '<C-]>', '<C-i>', { noremap = true, silent = true })

-- Window width adjustment
map("n", "<C-,>", "<C-w><", { desc = "Decrease window width" })
map("n", "<C-.>", "<C-w>>", { desc = "Increase window width" })
map("n", "<leader>w=", "<C-w>=", { desc = "Equalize window sizes" })

local function toggle_aider_repl()
  -- Check if the REPL window exists
  local bufnr = vim.fn.bufnr("aider")
  local winid = vim.fn.bufwinid(bufnr)

  -- If the REPL window is open
  if winid ~= -1 then
    -- Get the current window
    local current_win = vim.api.nvim_get_current_win()
    
    -- Check if we're currently in the REPL window
    if current_win == winid then
      local mode = vim.api.nvim_get_mode().mode
      
      -- If in terminal mode or insert mode, exit to normal mode first
      if mode == "t" or mode == "i" then
        vim.cmd("stopinsert")
      end
      
      -- Small delay to ensure mode change completes, then hide
      vim.defer_fn(function()
        vim.fn.feedkeys(vim.api.nvim_replace_termcodes("<Plug>(REPLHide-aider)", true, false, true), "")
      end, 10)
    else
      -- We're in a different window, just hide the REPL
      vim.fn.feedkeys(vim.api.nvim_replace_termcodes("<Plug>(REPLHide-aider)", true, false, true), "")
    end
  else
    -- If the REPL is not open, start it and enter insert mode
    -- Check if the REPL buffer exists
    if bufnr == -1 then
      -- Start the REPL and enter insert mode
      vim.fn.feedkeys(vim.api.nvim_replace_termcodes("<Plug>(REPLStart-aider)", true, false, true), "")
      vim.defer_fn(function()
        local repl_win = vim.fn.bufwinid("aider")
        if repl_win ~= -1 then
          vim.api.nvim_set_current_win(repl_win)
          vim.cmd("startinsert")
        end
      end, 100)
    else
      -- Focus the REPL window and enter insert mode if it's already open but not focused
      vim.fn.feedkeys(vim.api.nvim_replace_termcodes("<Plug>(REPLFocus-aider)", true, false, true), "")
      vim.defer_fn(function()
        local repl_win = vim.fn.bufwinid("aider")
        if repl_win ~= -1 then
          vim.api.nvim_set_current_win(repl_win)
          vim.cmd("startinsert")
        end
      end, 50)
    end
  end
end

-- Aider REPL keymaps
map("n", "<C-a>", toggle_aider_repl, { desc = "Toggle aider REPL" })
map("t", "<C-a>", toggle_aider_repl, { desc = "Toggle aider REPL" })

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
