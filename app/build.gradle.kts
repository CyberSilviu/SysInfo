plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.sysinfo.app"
    compileSdk = 34

    defaultConfig {
        minSdk = 26
        targetSdk = 34
        versionCode = 2
        versionName = "2.0"
    }

    flavorDimensions += "edition"
    productFlavors {
        create("pro") {
            dimension = "edition"
            applicationId = "com.zfinfo64.app"
            resValue("string", "app_name", "ZF-INFO64 Pro")
            buildConfigField("boolean", "IS_FREE", "false")
        }
        create("free") {
            dimension = "edition"
            applicationId = "com.zfinfo64.app.free"
            resValue("string", "app_name", "ZF-INFO64 Free")
            buildConfigField("boolean", "IS_FREE", "true")
        }
    }

    signingConfigs {
        create("release") {
            storeFile = file("../sysinfo-release.jks")
            storePassword = "sysinfo123"
            keyAlias = "sysinfo"
            keyPassword = "sysinfo123"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            signingConfig = signingConfigs.getByName("release")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    buildFeatures {
        viewBinding = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // AndroidX Core
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")

    // Navigation
    implementation("androidx.navigation:navigation-fragment-ktx:2.7.7")
    implementation("androidx.navigation:navigation-ui-ktx:2.7.7")

    // Lifecycle
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.7.0")
    implementation("androidx.lifecycle:lifecycle-livedata-ktx:2.7.0")

    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")

    // Charts (MPAndroidChart)
    implementation("com.github.PhilJay:MPAndroidChart:v3.1.0")

    // RecyclerView
    implementation("androidx.recyclerview:recyclerview:1.3.2")

    // CardView
    implementation("androidx.cardview:cardview:1.0.0")
}
