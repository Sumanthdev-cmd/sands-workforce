package in.sandssoftware.workforce;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONObject;

/** Keystore-backed encryption, including the offline queue. Excluded from backups. */
public final class SecureStore {
    private static final String ALIAS = "sands.workforce.session.v1";
    private final SharedPreferences preferences;
    private final SecretKey key;
    public SecureStore(Context c) {
        try {
            preferences = c.getSharedPreferences("secure_v1", Context.MODE_PRIVATE);
            KeyStore ks = KeyStore.getInstance("AndroidKeyStore"); ks.load(null);
            if (!ks.containsAlias(ALIAS)) {
                KeyGenerator g = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
                g.init(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
                g.generateKey();
            }
            key = (SecretKey) ks.getKey(ALIAS, null);
        } catch (Exception e) { throw new IllegalStateException("Secure device storage is unavailable.", e); }
    }
    public synchronized void put(String name, String value) {
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key);
            cipher.updateAAD(name.getBytes(StandardCharsets.UTF_8));
            String packed = Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + "." + Base64.encodeToString(cipher.doFinal(value.getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP);
            if (!preferences.edit().putString(name, packed).commit()) throw new IllegalStateException("Could not save secure state.");
        } catch (Exception e) { throw new IllegalStateException("Could not save secure state.", e); }
    }
    public synchronized String get(String name, String fallback) {
        String packed = preferences.getString(name, null);
        if (packed == null) return fallback;
        try {
            String[] parts = packed.split("\\.");
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
            cipher.updateAAD(name.getBytes(StandardCharsets.UTF_8));
            return new String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), StandardCharsets.UTF_8);
        } catch (Exception e) {
            preferences.edit().clear().commit();
            return fallback; // Invalidated keys fail closed, never recover unencrypted tokens.
        }
    }
    public synchronized JSONObject object(String name) {
        try { return new JSONObject(get(name, "{}")); } catch (Exception e) { return new JSONObject(); }
    }
    public synchronized void remove(String name) { preferences.edit().remove(name).commit(); }
}
