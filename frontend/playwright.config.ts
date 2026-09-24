import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'./e2e',workers:1,timeout:180000,
  use:{baseURL:'http://127.0.0.1:8000',headless:true,channel:process.env.CI ? undefined : 'chrome',screenshot:'only-on-failure'},
  reporter:[['list'],['json',{outputFile:'test-results/browser-results.json'}]],
});
