"use strict";


var gulp = require('gulp');
var gutil = require('gulp-util');
var uglify = require('gulp-uglify');
var concat = require('gulp-concat');
var rename = require('gulp-rename');
var merge = require('merge-stream');
var shell = require('gulp-shell');
var merge = require('merge-stream');
var exec = require('child_process').exec;
var execSync = require('child_process').execSync;
var fs = require('fs');
var path = require('path');
var del = require('del');
var _ = require('underscore');


// Script Inital Working Directory
var sonador_rootdir = process.cwd();


// Project Root Folders
var sonador_styles = './styles/';
var sonador_jslib = './sonador/jslib/';
var sonador_static = './sonador/static/';
var sonador_static_css = sonador_static+'css/';
var sonador_static_js = sonador_static+'js/';


// Guru/Base Dependencies
var guru_jslib = './lib/guru/jslib/';
var guru_static = './lib/guru/static/';
var guru_static_css = guru_static+'css/';
var guru_static_js = guru_static+'js/';


// Visionaire and OHIF
var visionaire_jslib = './apps/visionaire/jslib/';
var visionaire_jslib_ohif = visionaire_jslib+'ohif/';
var visionaire_static = './apps/visionaire/static/';
var visionaire_static_css = visionaire_static+'css/';
var visionaire_static_js = visionaire_static+'js/';

var visionaire_jslib_extensions = visionaire_jslib_ohif+'extensions/';
var visionaire_jslib_vtk = visionaire_jslib_extensions+'vtk/';
var visionaire_jslib_microscopy = visionaire_jslib_extensions+'dicom-microscopy/';
var visionaire_jslib_cornerstone = visionaire_jslib_extensions+'cornerstone/';
var visionaire_jslib_segmentation = visionaire_jslib_extensions+'dicom-segmentation/';
var visionaire_jslib_html = visionaire_jslib_extensions+'dicom-html/';
var visionaire_jslib_p10 = visionaire_jslib_extensions+'dicom-p10-downloader/';
var visionaire_jslib_pdf = visionaire_jslib_extensions+'dicom-pdf/';
var visionaire_jslib_rt = visionaire_jslib_extensions+'dicom-rt/';
var visionaire_jslib_tracker = visionaire_jslib_extensions+'lesion-tracker/';



// Content Widgets
var content_jslib = './lib/content/jslib/';
var content_jslib_ace = content_jslib+'ace/';
var content_static = './lib/content/static/';
var content_static_js = content_static+'js/';
var content_static_css = content_static+'css/';



// Build and compile standalone OHIF components

function jsBuildOHIFViewer(done){
	console.log('Compile and copy OHIF: ', visionaire_jslib_ohif);

	var visionaire_jslib_ohif_node_deps = visionaire_jslib_ohif+'node_modules/';
	var ohif_deps, build_ohif;

	try {

		// Determine if necessary dependencies are installed
		ohif_deps = fs.lstatSync(visionaire_jslib_ohif_node_deps);
		build_ohif = true;

	} catch(err) {

		// Dependencies not yet installed, change to Foundation directory and install
		try {
			console.info('Dependencies for OHIF have not yet been installed. Install to: ',
				visionaire_jslib_ohif_node_deps);
			process.chdir(visionaire_jslib_ohif);
			execSync('yarn config set workspaces-experimental true')
			execSync('yarn install')
			console.info('OHIF dependencies installed successfully');
			build_ohif = true;
			process.chdir(sonador_rootdir);

		} catch(err) {

			// Indicate that an error occurred, stop build
			console.error('Error occurrered while trying to install node dependencies: ', err);
			process.chdir(sonador_rootdir);
			return done();

		}
	} finally {

		if (build_ohif) { 
			try {
				process.chdir(visionaire_jslib_ohif);

				// Execute Foundation build script
				console.info('Build OHIF with default options');
				execSync('yarn build:package');
				console.info('Build of OHIF completed successfully');

				process.chdir(sonador_rootdir);
			} catch(err){

				// Indicate that an error occurred, stop build
				console.error('Error while trying to build OHIF: ', err);
				process.chdir(sonador_rootdir);

				return done();
			}
		}
	}

	return gulp.src(visionaire_jslib_ohif+'platform/viewer/dist/**/*').pipe(gulp.dest(visionaire_static_js+'ohif/'));
}


function jsBuildVTK(done) {
	console.log('Compile and copy VTK: ', visionaire_jslib_vtk);

	var visionaire_jslib_vtk_node_deps = visionaire_jslib_vtk+'node_modules/';
	var vtk_deps, build_vtk;

	try {

		// Determine if necessary dependencies are installed
		vtk_deps = fs.lstatSync(visionaire_jslib_vtk_node_deps);
		build_vtk = true;

	} catch(err) {

		// Dependencies not yet installed, change to Foundation directory and install
		try {
			console.info('Dependencies for OHIF have not yet been installed. Install to: ',
				visionaire_jslib_vtk_node_deps);
			process.chdir(visionaire_jslib_vtk);
			execSync('yarn install');
			console.info('OHIF dependencies installed successfully');
			build_vtk = true;
			process.chdir(sonador_rootdir);
		} catch(err) {

			// Indicate that an error occurred, stop build
			console.error('Error occurrered while trying to install node dependencies: ', err);
			process.chdir(sonador_rootdir);
			return done();
		}
	} finally {

		if (build_vtk) {
			try {
				process.chdir(visionaire_jslib_vtk);

				// Execute Foundation build script
				console.info('Build VTK with default options');
				execSync('yarn run build');
				console.info('Build of VTK completed successfully');

				process.chdir(sonador_rootdir);
			} catch(err){

				// Indicate that an error occurred, stop build
				console.error('Error while trying to build VTK: ', err);
				process.chdir(sonador_rootdir);
				return done();
			}
		}
	}

	return gulp.src(visionaire_jslib_vtk+'dist/**/*').pipe(gulp.dest(visionaire_static_js+'ohif/vtk/'));
}


function jsBuildMicroscopy(done) {
	console.log('Compile and copy DICOM Microscopy: ', visionaire_jslib_microscopy);

	var visionaire_jslib_microscopy_node_deps = visionaire_jslib_microscopy+'node_modules/';
	var micro_deps, build_micro;

	try {

		// Determine if necessary dependencies are installed
		micro_deps = fs.lstatSync(visionaire_jslib_microscopy_node_deps);
		build_micro = true;

	} catch(err) {

		// Dependencies not yet installed, change to Foundation directory and install
		try {
			console.info('Dependencies for OHIF have not yet been installed. Install to: ',
				visionaire_jslib_microscopy_node_deps);
			process.chdir(visionaire_jslib_microscopy);
			execSync('yarn install');
			console.info('OHIF DCM microscopy dependencies installed successfully');
			build_micro = true;
			process.chdir(sonador_rootdir);

		} catch(err) {

			// Indicate that an error occurred, stop build
			console.error('Error occurrered while trying to install node dependencies: ', err);
			process.chdir(sonador_rootdir);
			return done();
		}
	} finally {

		if (build_micro) {
			try {
				process.chdir(visionaire_jslib_microscopy);

				// Execute Foundation build script
				console.info('Build DCM microscopy extension with default options');
				execSync('yarn run build');
				console.info('Build of DCM microscopy extension completed successfully');

				process.chdir(sonador_rootdir);
			} catch(err){

				// Indicate that an error occurred, stop build
				console.error('Error while trying to build DCM microscopy extension: ', err);
				process.chdir(sonador_rootdir);

				return done();
			}
		}
	}

	return gulp.src(visionaire_jslib_microscopy+'dist/**/*').pipe(gulp.dest(visionaire_static_js+'ohif/microscopy/'));
}


function jsBuildCornerstone(done) {
	console.log('Compile and copy DICOM Cornerstone Toolkit: ', visionaire_jslib_cornerstone);

	var visionaire_jslib_cornerstone_node_deps = visionaire_jslib_cornerstone+'node_modules/';
	var cornerstone_deps, build_cornerstone;

	try {

		// Determine if necessary dependencies are installed
		cornerstone_deps = fs.lstatSync(visionaire_jslib_cornerstone_node_deps);
		build_cornerstone = true;

	} catch(err) {

		// Dependencies not yet installed, change to Foundation directory and install
		try {
			console.info('Dependencies for OHIF Cornerstone Toolkit extension have not yet been installed. Install to: ',
				visionaire_jslib_cornerstone_node_deps);
			process.chdir(visionaire_jslib_cornerstone);
			execSync('yarn install');
			console.info('OHIF cornerstone extension dependencies installed successfully');
			build_cornerstone = true;
			process.chdir(sonador_rootdir);

		} catch(err) {

			// Indicate that an error occurred, stop build
			console.error('Error occurrered while trying to install node dependencies: ', err);
			process.chdir(sonador_rootdir);
			return done();
		}
	} finally {

		if (build_cornerstone) {
			try {
				process.chdir(visionaire_jslib_cornerstone);

				// Execute Foundation build script
				console.info('Build Cornerstone extension with default options');
				execSync('yarn run build');
				console.info('Build of Cornerstone extension completed successfully');

				process.chdir(sonador_rootdir);
			} catch(err){

				// Indicate that an error occurred, stop build
				console.error('Error while trying to build Cornerstone extension: ', err);
				process.chdir(sonador_rootdir);
				return done();
			}
		}
	}

	return gulp.src(visionaire_jslib_cornerstone+'dist/**/*').pipe(gulp.dest(visionaire_static_js+'ohif/cornerstone/'));
}


function jsBuildDCMSegmentation(done) {
	console.log('Compile and copy DICOM Segmentation extension: ', visionaire_jslib_segmentation);

	var visionaire_jslib_segmentation_node_deps = visionaire_jslib_segmentation+'node_modules/';
	var seg_deps, build_seg;

	try {

		// Determine if necessary dependencies are installed
		seg_deps = fs.lstatSync(visionaire_jslib_segmentation_node_deps);
		build_seg = true;

	} catch(err) {

		// Dependencies not yet installed, change to Foundation directory and install
		try {
			console.info('Dependencies for OHIF Cornerstone Toolkit extension have not yet been installed. Install to: ',
				visionaire_jslib_segmentation_node_deps);
			process.chdir(visionaire_jslib_segmentation);
			execSync('yarn install');
			console.info('OHIF segmentation extension dependencies installed successfully');
			build_seg = true;
			process.chdir(sonador_rootdir);

		} catch(err) {

			// Indicate that an error occurred, stop build
			console.error('Error occurrered while trying to install node dependencies: ', err);
			process.chdir(sonador_rootdir);
			return done();
		}
	} finally {

		if (build_seg) {
			try {
				process.chdir(visionaire_jslib_segmentation);

				// Execute Foundation build script
				console.info('Build segmentation extension with default options');
				execSync('yarn run build');
				console.info('Build of segmentation extension completed successfully');

				process.chdir(sonador_rootdir);
			} catch(err){

				// Indicate that an error occurred, stop build
				console.error('Error while trying to build segmentation extension: ', err);
				process.chdir(sonador_rootdir);

				return done();
			}
		}
	}

	return gulp.src(visionaire_jslib_segmentation+'dist/**/*').pipe(gulp.dest(visionaire_static_js+'ohif/segmentation/'));
}


// Deploy static assets
var ohif_jsfolders = {
	viewer: {
		src: visionaire_jslib_ohif, 
		build: visionaire_jslib_ohif+'platform/viewer/dist/*',
		dst: visionaire_static_js+'ohif/'
	},
	cornerstone: {
		src: visionaire_jslib_cornerstone,
		build: visionaire_jslib_cornerstone+'dist/**/*',
		dst: visionaire_static_js+'ohif/cornerstone/'
	},
	segmentation: {
		src: visionaire_jslib_segmentation,
		build: visionaire_jslib_segmentation+'dist/**/*',
		dst: visionaire_static_js+'ohif/segmentation/'
	},
	microscopy: {
		src: visionaire_jslib_microscopy,
		build: visionaire_jslib_microscopy+'dist/**/*',
		dst: visionaire_static_js+'ohif/microscopy/',
	},
	vtk: {
		src: visionaire_jslib_vtk, 
		build: visionaire_jslib_vtk+'dist/**/*',
		dst: visionaire_static_js+'ohif/vtk/',
	},
	html: {
		src: visionaire_jslib_html,
		build: visionaire_jslib_html+'dist/**/*',
		dst: visionaire_static_js+'ohif/html/',
	},
	pdf: {
		src: visionaire_jslib_pdf,
		build: visionaire_jslib_pdf+'dist/**/*',
		dst: visionaire_static_js+'ohif/pdf/',
	},
	rt: {
		src: visionaire_jslib_rt,
		build: visionaire_jslib_rt+'dist/**/*',
		dst: visionaire_static_js+'ohif/rt/',
	},
	tracker: {
		src: visionaire_jslib_tracker,
		build: visionaire_jslib_tracker+'dist/**/*',
		dst: visionaire_static_js+'ohif/tracker/',
	}
}


function buildOHIF(done) {
	console.log('Compile and copy OHIF platform (viewer and extensions): ', visionaire_jslib_ohif);

	var visionaire_jslib_ohif_node_deps = visionaire_jslib_ohif+'node_modules/';
	var ohif_deps, build_ohif;

	try {

		// Determine if necessary dependencies are installed
		ohif_deps = fs.lstatSync(visionaire_jslib_ohif_node_deps);
		build_ohif = true;

	} catch(err) {

		// Dependencies not yet installed, change to Foundation directory and install
		try {
			console.info('Dependencies for OHIF have not yet been installed. Install to: ',
				visionaire_jslib_ohif_node_deps);
			process.chdir(visionaire_jslib_ohif);
			execSync('yarn config set workspaces-experimental true')
			execSync('yarn install')
			console.info('OHIF dependencies installed successfully');
			build_ohif = true;
			process.chdir(sonador_rootdir);

		} catch(err) {

			// Indicate that an error occurred, stop build
			console.error('Error occurrered while trying to install node dependencies: ', err);
			process.chdir(sonador_rootdir);
			return done();

		}
	} finally {

		if (build_ohif) { 
			try {
				process.chdir(visionaire_jslib_ohif);

				// Execute Foundation build script
				console.info('Build OHIF platform with default options');
				execSync('yarn build:package-all');
				console.info('Build of OHIF completed successfully');

				process.chdir(sonador_rootdir);
			} catch(err){

				// Indicate that an error occurred, stop build
				console.error('Error while trying to build OHIF: ', err);
				process.chdir(sonador_rootdir);

				return done();
			}
		}
	}

	done();
}

function deployOHIF(done) {
	console.info('Deploy compiled JavaScript OHIF assets to static folders');
	var tasks = _.keys(ohif_jsfolders).map(function(f) {
		console.info('Copy files for', f, 'from', ohif_jsfolders[f].build, 'to', ohif_jsfolders[f].dst);
		return gulp.src(ohif_jsfolders[f].build).pipe(gulp.dest(ohif_jsfolders[f].dst));
	});

	return merge(tasks);
}


function jsBuildAce(done) {
	console.log('Compile and minify ACE code editor: ', content_jslib_ace);
	var content_jslib_ace_node_deps = content_jslib_ace+'node_modules/';
	var ace_deps, build_ace;

	try{

		//
		ace_deps = fs.lstatSync(content_jslib_ace_node_deps);
		build_ace = true;

	} catch (err) {

		// Dependencies not yet installed, cahnge to jslib directory and install
		try {

			console.info('Dependencies for ACE JS have not yet been installed. Install to ',
				content_jslib_ace_node_deps);
			process.chdir(content_jslib_ace);
			execSync('npm install');
			console.info('ACE JS depdencies installed succesfully');
			build_ace = true;
			process.chdir(sonador_rootdir);
		} catch (err) {

			// Indicate that an error occurred, stop build
			console.log('Error while trying to install node dependencies: ', err);
			process.chdir(sonador_rootdir);
			done();
		}
	} finally {

		if (build_ace) {
			try {
				process.chdir(content_jslib_ace);

				// Execue ACE build script
				console.log('Build ACE JS with default options');
				execSync('node ./Makefile.dryice.js');
				console.info('Build of ACE JS completed succesfully');

				process.chdir(sonador_rootdir);
			} catch (err) {

				// Indicate that an error occurred, stop build
				console.log('Error while trying to build ACE JS: ', err);
				process.chdir(sonador_rootdir);
				done();
			}
		} else { done(); }
	}

	return gulp.src(content_jslib_ace+'build/src/**/*.js')
		.pipe(gulp.dest(content_static_js+'ace/'));
}


// Compile 
const js = gulp.series(buildOHIF, deployOHIF, jsBuildAce);
const jsCoreDeps = gulp.series(jsBuildOHIFViewer, jsBuildCornerstone, jsBuildDCMSegmentation, jsBuildAce)


// Gulp Tasks
exports.jsBuildOHIFViewer = jsBuildOHIFViewer;
exports.jsBuildVTK = jsBuildVTK;
exports.jsBuildMicroscopy = jsBuildMicroscopy;
exports.jsBuildCornerstone = jsBuildCornerstone;
exports.jsBuildDCMSegmentation = jsBuildDCMSegmentation;
exports.buildOHIF = buildOHIF;
exports.deployOHIF = deployOHIF;
exports.jsBuildAce = jsBuildAce;
exports.jsCoreDeps = jsCoreDeps;
exports.js = js;
