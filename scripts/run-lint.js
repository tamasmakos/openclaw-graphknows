import { activate } from "../index.js";
const vaultPath = process.argv[2];
const plugin = activate({ vaultPath });
const lint = await plugin.commands.lint();
console.log(JSON.stringify(lint.issues, null, 2));
