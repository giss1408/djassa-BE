# Releasing the apps on Google Play

Step by step, for the first release and every one after it. What the forms
ask and why (signing, Data safety, App content) is in
[PLAY-STORE.md](PLAY-STORE.md); this page is the order to do things in.

| App | Package (permanent) | Repository | Signing key on the release Mac |
|---|---|---|---|
| Fidelia (customers) | `com.regisse.fidelia` | djassa-App-user | `~/djassa-user-release.jks` |
| Fidelia Pro (merchants) | `com.regisse.fidelia.pro` | djassa-App-retailer | `~/djassa-merchant-release.jks` |

The keys' aliases and passwords live in the team's password manager (they
are also the `ANDROID_*` GitHub secrets). Without a key and its passwords no
update of that app can ever be published: keep a backup.

## 0. Before the first release (once)

1. **Protect the keys.** `chmod 600 ~/djassa-*-release.jks`. Move the
   passwords from any plain-text file (`~/djassa-*-github-secrets.txt`) into
   the password manager, then delete that file.
2. **Privacy policy**: fill in the legal entity and its address in fidelia-Web
   `public/confidentialite/index.html` (search for `A-COMPLETER`), deploy, and
   check the page loads.
3. **Decide the server** the build talks to: the repository variable
   `FIDELIA_API_BASE` in each app repository (Settings → Secrets and variables
   → Actions → Variables). Today it is the **test** API: shared test numbers,
   no real SMS, simulated payments. Fine for internal testing; real merchants
   and customers need the production API (`PRODUCTION.md`).

## 1. Build the release

From `integration` (test) or `trunk` (production), in each app repository:

```bash
git checkout integration && git pull
git tag vX.Y.Z && git push origin vX.Y.Z      # the next version, e.g. v0.2.1
```

The workflow **Release APKs** builds, signs and publishes:

* the APKs, as a public GitHub Release (the website's `/app/` download page
  serves the latest one);
* the **Play bundle**, as the run's artifact `play-bundle-<version>-<number>`
  (kept 90 days, never public).

Check the run is green in the repository's **Actions** tab. The version code
is the run number, so it always goes up, as Play requires.

The first Play release can use v0.2.0, already built on 9 October 2026:
[merchant run](https://github.com/giss1408/djassa-App-retailer/actions/runs/37976965256),
[customer run](https://github.com/giss1408/djassa-App-user/actions/runs/37976972377).

## 2. Create each app in Play Console (first release only)

1. **Create app**: name *Fidelia* or *Fidelia Pro*, default language
   **French (France) – fr-FR**, **App**, **Free**. Accept the declarations.
2. **Store presence → Main store listing**: copy from the app repository,
   `android/fastlane/metadata/android/fr-FR/`:
   * `title.txt`, `short_description.txt`, `full_description.txt`;
   * `images/icon.png` (app icon) and `images/featureGraphic.png`;
   * `images/phoneScreenshots/*.png` (phone screenshots, in order).
   Category: *Shopping* (Fidelia) or *Business* (Fidelia Pro). Contact email:
   `contact.fidelia@regisse.com`.
3. **Policy → App content**: answer each form as in PLAY-STORE.md § 5,
   including Data safety. Links to give:
   * privacy policy: `https://<site>/confidentialite/`
   * account deletion: `https://<site>/supprimer-mon-compte/`
   (`<site>` = the public site; the Render address until the domain exists).

## 3. Upload to internal testing

1. Download the bundle: open the release run (Actions tab, signed in to
   GitHub), **Artifacts** → `play-bundle-…`, unzip → `app-release.aab`.
2. Play Console → the app → **Test and release → Testing → Internal testing →
   Create new release**.
3. **App signing (first release only)**: choose **Use a different key →
   Export and upload a key from Java keystore**. Play gives a download link for
   its PEPK tool and a command; run it on the release Mac with the matching
   `.jks` and its alias, and upload the `.zip` it writes. Play then signs every
   install with **our** key, so the website APKs and the Play version update
   each other. (If Play generates its own key instead, testers must uninstall
   the website APK first.)
4. Upload `app-release.aab`.
5. **Release notes** (French): the version's lines from the app's
   `CHANGELOG.md`, shortened to 500 characters, or
   `android/fastlane/metadata/android/fr-FR/changelogs/default.txt`.
6. **Testers**: create an email list (the team), save, and share the opt-in
   link. Testers open it on their phone, accept, then install from Play.
7. **Save → Review release → Start rollout to Internal testing.** Internal
   tests are available within minutes, without Google's review.

## 4. The pilot: closed testing

A personal developer account must run a closed test with **at least 12
testers opted in for 14 consecutive days** before it can publish to
everyone. The pilot is that test:

1. Point `FIDELIA_API_BASE` at the production API and tag a new version.
2. **Testing → Closed testing → Create track** (e.g. *Pilote Abidjan*), upload
   the new bundle, add the pilot merchants, their cashiers and the team as
   testers (email list or Google Group), share the opt-in link on WhatsApp.
3. Closed tests go through Google's review (from a few hours to a few days).
4. After 14 days with 12 or more testers, **Production** unlocks: apply for
   production access in the Dashboard.

## 5. Every later release

1. Add the version's section to the app's `CHANGELOG.md` and update
   `changelogs/default.txt`.
2. Tag the next version (step 1).
3. Download the new bundle and create a release on the same track (step 3,
   without the signing part). Use **Promote release** to move a tested build
   from internal to closed testing, or to production.
4. Keep the website APKs and Play on the same version: both come from the
   same tag.

## If something goes wrong

| Problem | Cause and fix |
|---|---|
| Play: *version code already used* | A bundle from an older run. Use the newest run's artifact, or tag a new version. |
| Play: *wrong signing key* | The bundle was signed with another key. It must be signed by the release key in the GitHub secrets; check the run used them (the workflow refuses to build unsigned). |
| Play: *target API level* | Both apps target API 36; a build from before v0.2.0 does not qualify. |
| Testers do not see the app | They must open the opt-in link **with the Google account** on their phone, accept, then search or follow the Play link. |
| Sign-in fails for real users | The build talks to the test API, which sends no SMS. Use a production build (step 4). |
