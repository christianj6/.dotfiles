require "nvchad.mappings"

-- add yours here

local map = vim.keymap.set

map("n", ";", ":", { desc = "CMD enter command mode" })

-- map("i", "jk", "<ESC>")
-- map({ "n", "i", "v" }, "<C-s>", "<cmd> w <cr>")

local function toggle_aider_repl()
  -- Check if the REPL window exists
  local bufnr = vim.fn.bufnr("aider")
  local winid = vim.fn.bufwinid(bufnr)

  -- If the REPL window is open
  if winid ~= -1 then
    local mode = vim.api.nvim_get_mode().mode  -- Get current mode (normal, insert, etc.)

    -- If we are in insert mode inside the REPL, exit insert mode and hide the REPL window
    if mode == "i" then
      vim.cmd("stopinsert")  -- Exit insert mode
      -- Hide the REPL window
      vim.fn.feedkeys(vim.api.nvim_replace_termcodes("<Plug>(REPLHide-aider)", true, false, true), "")
    else
      -- If we're in normal mode in the REPL, hide the REPL window
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
          vim.cmd("startinsert")  -- Enter insert mode automatically
        end
      end, 100)
    else
      -- Focus the REPL window and enter insert mode if it's already open but not focused
      vim.fn.feedkeys(vim.api.nvim_replace_termcodes("<Plug>(REPLFocus-aider)", true, false, true), "")
      vim.defer_fn(function()
        local repl_win = vim.fn.bufwinid("aider")
        if repl_win ~= -1 then
          vim.api.nvim_set_current_win(repl_win)
          vim.cmd("startinsert")  -- Enter insert mode automatically
        end
      end, 50)
    end
  end
end

-- Aider REPL keymaps
map("n", "<C-a>", toggle_aider_repl, { desc = "Toggle aider REPL" })

-- Build script shortcut 
map("n", "<leader>b", function ()
  local dir vim.fn.expand("%:p:h")
  local output = vim.fn.systemlist("./build.sh")
  vim.cmd("botright new")
  vim.api.nvim_buf_set_lines(0, 0, -1, false, output)
  vim.bo.buftype = "nofile"
  vim.bo.bufhidden = "wipe"
  vim.bo.swapfile = false
  vim.bo.readonly = true
  vim.bo.filetype = "output"

  map("n", "q", "<cmd>bd!<CR>", {buffer=true})
end, {desc="Run build.sh"}
)

-- map("n", "<Leader>as", "<Plug>(REPLStart-aider)", { desc = "Start an aider REPL" })
-- map("n", "<Leader>af", "<Plug>(REPLFocus-aider)", { desc = "Focus on aider REPL" })
-- map("n", "<Leader>ah", "<Plug>(REPLHide-aider)", { desc = "Hide aider REPL" })
-- map("v", "<Leader>ar", "<Plug>(REPLSendVisual-aider)", { desc = "Send visual region to aider" })
-- map("n", "<Leader>arr", "<Plug>(REPLSendLine-aider)", { desc = "Send lines to aider" })
-- map("n", "<Leader>ar", "<Plug>(REPLSendOperator-aider)", { desc = "Send Operator to aider" })

