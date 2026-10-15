// Test seam: the actual bridge talks to an installed Runtime in a disposable profile.
import { bridge } from '../integrations/managed/bridge.mjs';
await bridge(async () => JSON.parse(process.env.QDRANT_TEST_BACKEND));
